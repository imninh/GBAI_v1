"""Nạp dữ liệu nền và dữ liệu demo cho GreenBin AI.

    python scripts/seed.py              # chỉ dữ liệu nền (danh mục, toà, tài khoản, quy định)
    python scripts/seed.py --demo       # thêm dữ liệu mô phỏng cho trang Vận hành / Chất lượng AI
    python scripts/seed.py --reset      # xoá sạch rồi nạp lại

**Mọi bản ghi mô phỏng đều gắn cờ ``is_seed=True``** và UI hiển thị nhãn
"dữ liệu demo mô phỏng" cho chúng. Số mô phỏng và số đo thật không được trộn
vào nhau mà không nói gì — đó là ranh giới không được vượt.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from src.config import get_settings  # noqa: E402
from src.db.models import (  # noqa: E402
    AgentRun,
    Alert,
    Base,
    Building,
    Classification,
    CollectionSchedule,
    EvalRun,
    FailureCase,
    KnowledgeChunk,
    KnowledgeDoc,
    PickupEvent,
    PickupRequest,
    RunNodeMetric,
    Unit,
    User,
    WasteCategory,
)
from src.db.seed_data import (  # noqa: E402
    BUILDINGS,
    COLLECTION_SCHEDULES,
    DEMO_PASSWORD,
    KNOWLEDGE_DOCS,
    UNITS,
    USERS,
    WASTE_CATEGORIES,
    gan_thung_demo,
    seed_bins,
    to_chuc_demo,
)
from src.db.session import get_engine, init_db, session_scope  # noqa: E402
from src.services.classifier import TIER_T0_CACHE, TIER_T05_LOCAL, TIER_T1, TIER_T2  # noqa: E402
from src.services.pickup_lifecycle import (  # noqa: E402
    CHO_DUYET,
    CHO_NHAN,
    DA_GIAO_DON_VI,
    HOAN_TAT,
)
from src.services.security import hash_password  # noqa: E402

random.seed(20260801)  # để mỗi lần seed cho ra cùng một bộ số, demo không nhảy múa


# --- Dữ liệu nền ---------------------------------------------------------


def seed_categories(session: Session) -> None:
    for row in WASTE_CATEGORIES:
        existing = session.scalar(select(WasteCategory).where(WasteCategory.code == row["code"]))
        if existing is None:
            session.add(WasteCategory(**row))
        else:
            for key, value in row.items():
                setattr(existing, key, value)
    session.flush()


def seed_buildings(session: Session) -> dict[str, Building]:
    result: dict[str, Building] = {}
    for row in BUILDINGS:
        building = session.scalar(select(Building).where(Building.code == row["code"]))
        if building is None:
            building = Building(**row)
            session.add(building)
        session.flush()
        result[building.code] = building
    return result


def seed_units(session: Session, buildings: dict[str, Building]) -> dict[str, Unit]:
    result: dict[str, Unit] = {}
    for row in UNITS:
        unit = session.scalar(select(Unit).where(Unit.code == row["code"]))
        if unit is None:
            unit = Unit(building_id=buildings[row["building_code"]].id, code=row["code"])
            session.add(unit)
        session.flush()
        result[unit.code] = unit
    return result


def seed_users(session: Session, units: dict[str, Unit]) -> dict[str, User]:
    result: dict[str, User] = {}
    # Băm một lần rồi dùng lại: mọi tài khoản demo chung một mật khẩu, mà
    # PBKDF2 200k vòng nhân với số tài khoản là phần chậm nhất của việc seed.
    mat_khau_da_bam = hash_password(DEMO_PASSWORD)
    for row in USERS:
        user = session.scalar(select(User).where(User.email == row["email"]))
        unit = units.get(row["unit_code"]) if row["unit_code"] else None
        if user is None:
            user = User(
                email=row["email"],
                phone=row["phone"],
                full_name=row["full_name"],
                role=row["role"],
                password_hash=mat_khau_da_bam,
                unit_id=unit.id if unit else None,
                green_points=row["green_points"],
            )
            session.add(user)
        elif not user.phone:
            # Tài khoản demo đã tồn tại từ trước khi có cột `phone`: điền số vào,
            # nhưng KHÔNG ghi đè số người dùng tự đặt.
            user.phone = row["phone"]
        session.flush()
        result[user.email] = user
    return result


def seed_schedules(session: Session, buildings: dict[str, Building]) -> None:
    for row in COLLECTION_SCHEDULES:
        building = buildings[row["building_code"]]
        existing = session.scalar(
            select(CollectionSchedule).where(
                CollectionSchedule.building_id == building.id,
                CollectionSchedule.category_code == row["category_code"],
            )
        )
        if existing is None:
            session.add(
                CollectionSchedule(
                    building_id=building.id,
                    category_code=row["category_code"],
                    weekdays=row["weekdays"],
                    window=row["window"],
                    location=row["location"],
                )
            )
    session.flush()


def seed_knowledge(session: Session, buildings: dict[str, Building]) -> None:
    for row in KNOWLEDGE_DOCS:
        doc = session.scalar(select(KnowledgeDoc).where(KnowledgeDoc.title == row["title"]))
        if doc is None:
            building = buildings.get(row["building_code"]) if row["building_code"] else None
            doc = KnowledgeDoc(
                building_id=building.id if building else None,
                title=row["title"],
                source=row["source"],
                doc_type=row["doc_type"],
                effective_date=date.fromisoformat(row["effective_date"]) if row["effective_date"] else None,
            )
            session.add(doc)
            session.flush()
        elif doc.source != row["source"]:
            doc.source = row["source"]

        expected_sections = {chunk["section"] for chunk in row["chunks"]}

        for chunk in row["chunks"]:
            existing_chunk = session.scalar(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.doc_id == doc.id,
                    KnowledgeChunk.section == chunk["section"],
                )
            )
            if existing_chunk is None:
                session.add(
                    KnowledgeChunk(
                        doc_id=doc.id,
                        content=chunk["content"],
                        section=chunk["section"],
                        meta={"needs_verification": bool(chunk.get("needs_verification"))},
                    )
                )
            else:
                existing_chunk.content = chunk["content"]
                existing_chunk.meta = {"needs_verification": bool(chunk.get("needs_verification"))}
        session.flush()

        stale = session.scalars(
            select(KnowledgeChunk).where(
                KnowledgeChunk.doc_id == doc.id,
                KnowledgeChunk.section.notin_(expected_sections),
            )
        ).all()
        for chunk in stale:
            print(f"  Xoá chunk cũ: doc={row['title']!r}, section={chunk.section!r}")
            session.delete(chunk)
        session.flush()


# --- Dữ liệu demo mô phỏng ----------------------------------------------

# Món rác mô phỏng: (tên, mã nhóm, nhóm người xác nhận nếu AI sai)
DEMO_ITEMS = [
    ("Hộp sữa giấy tráng nhôm", "recyclable_paper", "recyclable_metal"),
    ("Chai nước suối nhựa", "recyclable_plastic", None),
    ("Ly trà sữa có màng", "recyclable_plastic", "other"),
    ("Lon nước ngọt", "recyclable_metal", None),
    ("Chai thuỷ tinh", "recyclable_glass", None),
    ("Vỏ chuối", "organic", None),
    ("Cơm thừa", "organic", None),
    ("Khay cơm dính dầu", "other", "recyclable_plastic"),
    ("Hộp xốp đựng thức ăn", "other", None),
    ("Túi nilon đen", "other", None),
    ("Pin tiểu AA đã dùng", "hazardous", None),
    ("Bóng đèn huỳnh quang", "hazardous", None),
    ("Thùng carton lớn", "recyclable_paper", None),
    ("Tủ gỗ cũ", "bulky", None),
    ("Đệm cũ", "bulky", None),
]

TIER_MIX = [(TIER_T0_CACHE, 0.20), (TIER_T05_LOCAL, 0.12), (TIER_T1, 0.53), (TIER_T2, 0.15)]
TIER_COST = {TIER_T0_CACHE: 0.0, TIER_T05_LOCAL: 0.0, TIER_T1: 0.0018, TIER_T2: 0.0121}
TIER_LATENCY = {TIER_T0_CACHE: (10, 25), TIER_T05_LOCAL: (180, 420), TIER_T1: (900, 1800), TIER_T2: (1900, 3200)}


def _pick_tier() -> str:
    roll = random.random()
    total = 0.0
    for tier, share in TIER_MIX:
        total += share
        if roll <= total:
            return tier
    return TIER_T1


def da_co_du_lieu_demo(session: Session) -> bool:
    """Đã nạp dữ liệu mô phỏng lần nào chưa.

    Cần thiết vì máy chủ trên Render gọi ``bootstrap`` mỗi lần khởi động, mà
    khác với nhóm hàm dữ liệu nền, các hàm demo dưới đây sinh bản ghi mới chứ
    không cập nhật bản ghi cũ — không chặn thì mỗi lần restart lại nhân đôi.
    """
    return session.scalar(select(Classification.id).where(Classification.is_seed.is_(True)).limit(1)) is not None


def seed_demo_classifications(session: Session, count: int = 140) -> None:
    """Sinh lịch sử phân loại mô phỏng để các biểu đồ có hình dạng.

    Ràng buộc cố ý: **không bản ghi nào để rác nguy hại thành rác thường** —
    chỉ số an toàn cốt lõi phải bằng 0, và số 0 đó phải là sự thật của dữ liệu
    chứ không phải con số viết cứng trên giao diện.
    """
    categories = {c.code: c for c in session.scalars(select(WasteCategory)).all()}
    residents = session.scalars(select(User).where(User.role == "resident")).all()
    buildings = session.scalars(select(Building)).all()
    manager = session.scalar(select(User).where(User.role == "manager"))
    if not residents or not buildings:
        return

    now = datetime.now()
    for index in range(count):
        item_name, true_code, wrong_code = random.choice(DEMO_ITEMS)
        tier = _pick_tier()
        resident = random.choice(residents)
        building = random.choice(buildings)
        created = now - timedelta(days=random.randint(0, 13), hours=random.randint(0, 23))

        is_hazardous = categories[true_code].is_hazardous
        # Nhóm nguy hại luôn được model dự đoán đúng hoặc bị từ chối trả lời.
        refused = (index % 17 == 0) or (is_hazardous and random.random() < 0.15)
        predicted_code = true_code
        confidence = round(random.uniform(0.82, 0.97), 3)

        if refused:
            confidence = round(random.uniform(0.28, 0.58), 3)
        elif wrong_code and not is_hazardous and random.random() < 0.12:
            predicted_code = wrong_code
            confidence = round(random.uniform(0.62, 0.78), 3)

        latency_low, latency_high = TIER_LATENCY[tier]
        latency = random.randint(latency_low, latency_high)
        cost = TIER_COST[tier] * random.uniform(0.85, 1.2) if not refused else TIER_COST[tier]

        run = AgentRun(
            kind="classify",
            trigger="user",
            status="ok",
            items_processed=1,
            total_cost_usd=round(cost, 6),
            duration_ms=latency,
            started_at=created,
            finished_at=created + timedelta(milliseconds=latency),
            is_seed=True,
        )
        session.add(run)
        session.flush()

        session.add_all(
            [
                RunNodeMetric(run_id=run.id, node="safety_precheck", duration_ms=2, meta={"hard_block": ""}),
                RunNodeMetric(
                    run_id=run.id,
                    node="cache_lookup",
                    duration_ms=random.randint(8, 20),
                    cache_hits=1 if tier == TIER_T0_CACHE else 0,
                ),
                RunNodeMetric(
                    run_id=run.id,
                    node="classify_waste",
                    duration_ms=latency,
                    tokens_in=random.randint(700, 1100) if tier in {TIER_T1, TIER_T2} else 0,
                    tokens_out=random.randint(40, 90) if tier in {TIER_T1, TIER_T2} else 0,
                    cost_usd=round(cost, 6),
                    llm_calls=1 if tier in {TIER_T1, TIER_T2} else 0,
                    meta={"tier": tier},
                ),
                RunNodeMetric(run_id=run.id, node="safety_check", duration_ms=3),
                RunNodeMetric(
                    run_id=run.id,
                    node="advise",
                    status="skipped" if refused else "ok",
                    duration_ms=0 if refused else random.randint(250, 520),
                ),
            ]
        )

        classification = Classification(
            text_query=item_name if random.random() < 0.35 else "",
            input_type="text" if random.random() < 0.35 else "image",
            asker_id=resident.id,
            building_id=building.id,
            item_name="" if refused else item_name,
            predicted_category_id=None if refused else categories[predicted_code].id,
            confidence=confidence,
            tier=tier,
            model="demo-model",
            prompt_version="v1",
            refused=refused,
            refusal_reason="nghi_nguy_hai" if (refused and is_hazardous) else ("duoi_nguong" if refused else ""),
            escalated_to_human=refused,
            escalation_reason="Nghi rác nguy hại — luôn kiểm tra bằng model mạnh hơn" if tier == TIER_T2 else "",
            advice="" if refused else categories[predicted_code].handling_note,
            latency_ms=latency,
            cost_usd=round(cost, 6),
            run_id=run.id,
            is_seed=True,
            created_at=created,
        )

        # Khoảng 55% số ca đã có người xác nhận nhãn — đây là nguồn tính accuracy.
        if not refused and random.random() < 0.55:
            classification.human_label_id = categories[true_code].id
            classification.verified_by = manager.id if manager else None
            classification.verified_at = created + timedelta(hours=random.randint(1, 20))

        session.add(classification)
        session.flush()

        if classification.human_label_id and classification.human_label_id != classification.predicted_category_id:
            session.add(
                FailureCase(
                    classification_id=classification.id,
                    item_name=item_name,
                    true_category_code=true_code,
                    predicted_category_code=predicted_code,
                    confidence=confidence,
                    cause=random.choice(["chat_lieu_hon_hop", "vat_bi_che", "goc_chup_la", "anh_toi"]),
                    is_seed=True,
                    created_at=created,
                )
            )
    session.flush()


def seed_demo_pickups(session: Session) -> None:
    """Yêu cầu thu gom mô phỏng, đủ trạng thái để hàng đợi duyệt không rỗng."""
    from src.services import pickup as pickup_service

    residents = {u.email: u for u in session.scalars(select(User).where(User.role == "resident")).all()}
    manager = session.scalar(select(User).where(User.role == "manager"))
    cleaner = session.scalar(select(User).where(User.role == "cleaner"))
    if not residents or manager is None:
        return

    ngay_thu_gom = date.today() + timedelta(days=(3 - date.today().weekday()) % 7 or 7)

    ke_hoach = [
        ("resident@demo.vn", [("Tủ gỗ cũ", "bulky", 1), ("Thùng carton", "recyclable_paper", 2)], 48, "08:00-10:00", CHO_DUYET),
        ("resident2@demo.vn", [("Ghế sofa cũ", "bulky", 1)], 35, "08:00-10:00", CHO_NHAN),
        ("resident3@demo.vn", [("Đệm cũ", "bulky", 1)], 22, "08:00-10:00", CHO_NHAN),
        ("resident4@demo.vn", [("Bàn ăn hỏng", "bulky", 1)], 28, "08:00-10:00", CHO_NHAN),
        ("resident5@demo.vn", [("Thùng carton", "recyclable_paper", 6)], 12, "08:00-10:00", CHO_NHAN),
        ("resident6@demo.vn", [("Tủ lạnh mini hỏng", "bulky", 1)], 40, "14:00-16:00", CHO_DUYET),
        ("resident2@demo.vn", [("Quạt cây hỏng", "bulky", 1)], 8, "08:00-10:00", HOAN_TAT),
        # Yêu cầu này dừng ở `da_giao_don_vi` — đội vệ sinh đã chở tới nơi, chưa
        # ai cân. Nó là thứ nuôi hàng đợi "Chờ xác nhận khối lượng" trên console
        # đơn vị thu gom, và là thứ `scripts/chuan_bi_demo.py --lam` cần để có
        # việc mà làm. Không có nó thì đúng cái màn hình chứng minh nguyên tắc
        # "chỉ khối lượng người cân mới được dùng để chốt" lại là màn hình rỗng.
        ("resident@demo.vn", [("Máy giặt hỏng", "bulky", 1)], 55, "14:00-16:00", DA_GIAO_DON_VI),
    ]

    for email, items, weight, window, target_status in ke_hoach:
        resident = residents.get(email)
        if resident is None:
            continue
        request = pickup_service.create_pickup_request(
            session,
            resident=resident,
            items=[{"name": n, "category_code": c, "qty": q} for n, c, q in items],
            est_weight_kg=weight,
            preferred_date=ngay_thu_gom,
            preferred_window=window,
            note="Để ở sảnh tầng 1 giúp mình nhé.",
        )
        request.is_seed = True
        if target_status in {CHO_NHAN, HOAN_TAT, DA_GIAO_DON_VI} and request.status == CHO_DUYET:
            pickup_service.review_pickup(session, request=request, actor=manager, action="approve")
        if target_status == DA_GIAO_DON_VI:
            # Đi qua máy trạng thái thật từng bước (cho_nhan → da_nhan →
            # dang_van_chuyen → da_giao_don_vi) chứ không gán thẳng: mỗi bước ghi
            # một mốc `PickupEvent` nên lịch sử yêu cầu trên app cư dân trông như
            # một yêu cầu thật. Người thao tác là đội vệ sinh; chưa có tài khoản
            # vệ sinh thì dùng quản lý cho kịch bản demo.
            from src.services import pickup_flow
            from src.services.pickup_lifecycle import DA_NHAN, DANG_VAN_CHUYEN

            nguoi_thao_tac = cleaner or manager
            for den in (DA_NHAN, DANG_VAN_CHUYEN, DA_GIAO_DON_VI):
                pickup_flow.chuyen_trang_thai_yeu_cau(session, request, den, actor=nguoi_thao_tac)
        if target_status == HOAN_TAT:
            request.status = HOAN_TAT
            session.add(
                PickupEvent(request_id=request.id, kind="done", label_vi="Đội vệ sinh đã thu gom", actor_id=cleaner.id if cleaner else None)
            )
    session.flush()


def seed_demo_routes(session: Session) -> None:
    """Một tuyến đã chạy xong tuần trước, và một tuyến đang **chờ duyệt**.

    Tuyến chờ duyệt là nguyên liệu cho màn HITL #3 — nếu hàng đợi rỗng thì màn
    ăn điểm cao nhất của bài demo không có gì để xem.
    """
    from src.services import pickup as pickup_service
    from src.services import route_planner

    cleaner = session.scalar(select(User).where(User.role == "cleaner"))
    manager = session.scalar(select(User).where(User.role == "manager"))
    residents = {u.email: u for u in session.scalars(select(User).where(User.role == "resident")).all()}

    # --- Tuyến tuần trước: đã duyệt, đã thu xong ---
    ngay_cu = date.today() - timedelta(days=7)
    da_tao = []
    for email, weight in (("resident@demo.vn", 18), ("resident3@demo.vn", 24), ("resident5@demo.vn", 11)):
        resident = residents.get(email)
        if resident is None:
            continue
        request = pickup_service.create_pickup_request(
            session,
            resident=resident,
            items=[{"name": "Thùng carton gom lại", "category_code": "recyclable_paper", "qty": 3}],
            est_weight_kg=weight,
            preferred_date=ngay_cu,
            preferred_window="08:00-10:00",
        )
        request.is_seed = True
        if request.status == CHO_DUYET and manager is not None:
            pickup_service.review_pickup(session, request=request, actor=manager, action="approve")
        da_tao.append(request)

    if da_tao and manager is not None:
        try:
            tuyen_cu = route_planner.propose_route(
                session, service_date=ngay_cu, window="08:00-10:00", team_id=cleaner.id if cleaner else None
            )
            tuyen_cu.is_seed = True
            route_planner.review_route(session, route=tuyen_cu, actor=manager, action="approve")
            for stop in tuyen_cu.stops:
                route_planner.complete_stop(session, stop=stop, actor=cleaner or manager)
        except ValueError:
            pass

    # --- Tuyến sắp tới: để nguyên trạng thái chờ duyệt ---
    ngay = session.scalar(
        select(PickupRequest.preferred_date)
        .where(PickupRequest.status == CHO_NHAN, PickupRequest.preferred_date >= date.today())
        .limit(1)
    )
    if ngay is None:
        return
    try:
        route = route_planner.propose_route(
            session, service_date=ngay, window="08:00-10:00", team_id=cleaner.id if cleaner else None
        )
        route.is_seed = True
    except ValueError:
        return
    session.flush()


def seed_demo_eval(session: Session) -> None:
    """Kết quả eval mô phỏng, tách riêng bộ công khai và bộ ảnh tự chụp.

    Chênh lệch giữa hai cột là phát hiện đáng nói nhất của phần dữ liệu — con
    số ở đây phản ánh đúng khoảng cách miền đã khảo sát trong
    ``docs/research/sota-model-nhe-phan-loai-rac.md``.
    """
    if session.scalar(select(EvalRun).limit(1)) is not None:
        return
    session.add_all(
        [
            EvalRun(
                dataset="public",
                test_size=320,
                accuracy=0.912,
                macro_f1=0.884,
                hazard_recall=1.0,
                hazard_missed_count=0,
                retrieval_precision_at_5=0.86,
                prompt_version="v1",
                model="demo-model",
                avg_cost_usd=0.0021,
                p95_latency_ms=1840,
                is_seed=True,
            ),
            EvalRun(
                dataset="own",
                test_size=96,
                accuracy=0.734,
                macro_f1=0.701,
                hazard_recall=1.0,
                hazard_missed_count=0,
                retrieval_precision_at_5=0.86,
                prompt_version="v1",
                model="demo-model",
                avg_cost_usd=0.0024,
                p95_latency_ms=1910,
                is_seed=True,
            ),
        ]
    )
    session.flush()


def seed_demo_alerts(session: Session) -> None:
    if session.scalar(select(Alert).limit(1)) is not None:
        return
    building = session.scalar(select(Building).where(Building.code == "S1"))
    session.add(
        Alert(
            severity="warning",
            title="Tỉ lệ từ chối trả lời tuần này cao hơn tuần trước — kiểm tra chất lượng ảnh đầu vào",
            building_id=building.id if building else None,
            entity="classification",
            threshold="Ngưỡng cảnh báo: 8%",
            is_seed=True,
        )
    )
    session.flush()


# --- Chạy ----------------------------------------------------------------


def reset_database() -> None:
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _cho_phep_reset(url: str, toi_chac_chan: bool) -> bool:
    """Guard cho ``--reset``: sqlite luôn cho phép; non-sqlite cần HAI lớp.

    ``reset_database`` xoá sạch mọi bảng — đây là đường DUY NHẤT trong repo làm
    mất dữ liệu thật, và ngày 16/08/2026 CSDL đang chạy đã mất 600 tài khoản cư
    dân cùng toàn bộ bảng ``media``. Vì vậy một cờ dòng lệnh là chưa đủ:

    * lớp 1 — cờ ``--toi-chac-chan``;
    * lớp 2 — biến môi trường ``CHO_PHEP_XOA_DB=1``.

    Phải cố ý ở hai chỗ khác nhau thì lệnh xoá mới chạy. Trả về ``True`` nếu
    được phép, ``False`` nếu bị từ chối. Tách riêng để test được mà không cần
    ``main`` và không cần database thật.
    """
    if url.startswith("sqlite"):
        return True
    if not toi_chac_chan:
        return False
    return os.getenv("CHO_PHEP_XOA_DB", "") == "1"


def bootstrap(session: Session, *, demo: bool = False, count: int = 140) -> dict[str, int | bool]:
    """Nạp dữ liệu nền (và tuỳ chọn dữ liệu demo) vào một session có sẵn.

    Tách khỏi ``main`` để ``src/main.py`` gọi được lúc khởi động — trên Render
    không có chỗ chạy tay script này. **Gọi lại nhiều lần vô hại:** nhóm dữ liệu
    nền kiểm tra tồn tại trước khi thêm, còn nhóm demo bị chặn bởi
    ``da_co_du_lieu_demo``.

    Trả về tóm tắt để chỗ gọi tự quyết định in gì.
    """
    seed_categories(session)
    buildings = seed_buildings(session)
    units = seed_units(session, buildings)
    seed_users(session, units)
    seed_schedules(session, buildings)
    seed_knowledge(session, buildings)
    # Nằm ở khối dữ liệu NỀN chứ không ở nhánh demo: nhánh demo bị
    # ``da_co_du_lieu_demo`` chặn ngay từ lần chạy thứ hai, mà `data/app.db` và
    # Supabase đều đã qua lần đó từ lâu — để trong nhánh demo thì hai CSDL đang
    # chạy thật sẽ không bao giờ được gán thùng. Hàm này gọi lại vô hại.
    gan_thung_demo(session)
    # Gắn đơn vị thu gom cho nhân viên, quản lý và mọi thùng — cùng nằm ở khối
    # dữ liệu NỀN và cùng lý do: nhánh demo bị chặn từ lần chạy thứ hai, mà hai
    # CSDL đang chạy thật đều đã qua lần đó từ lâu. Gọi lại vô hại.
    to_chuc_demo(session)

    ket_qua: dict[str, int | bool] = {
        "categories": len(WASTE_CATEGORIES),
        "buildings": len(buildings),
        "users": len(USERS),
        "demo_da_nap": False,
        "demo_bo_qua": False,
    }
    if not demo:
        return ket_qua

    if da_co_du_lieu_demo(session):
        ket_qua["demo_bo_qua"] = True
        return ket_qua

    seed_demo_classifications(session, count=count)
    seed_demo_pickups(session)
    seed_demo_routes(session)
    seed_demo_eval(session)
    seed_demo_alerts(session)
    ket_qua["bins"] = seed_bins(session)
    # Gọi lần thứ hai, sau khi thùng vừa được tạo: lần gọi ở khối dữ liệu nền
    # phía trên chạy khi CSDL chưa có thùng nào nên không gán được gì.
    ket_qua["gan_thung"] = gan_thung_demo(session)
    # Cùng lý do: thùng vừa được tạo ở dòng trên nên lần gọi trong khối dữ liệu
    # nền chưa gắn được gì. Cư dân vẫn không bị gắn tổ chức.
    to_chuc_demo(session)
    ket_qua["demo_da_nap"] = count
    return ket_qua


def main() -> None:
    # Console Windows mặc định là cp1252, không in được tiếng Việt có dấu.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Nạp dữ liệu cho GreenBin AI")
    parser.add_argument("--demo", action="store_true", help="thêm dữ liệu mô phỏng cho trang Vận hành / Chất lượng AI")
    parser.add_argument("--reset", action="store_true", help="xoá sạch dữ liệu cũ trước khi nạp")
    parser.add_argument(
        "--toi-chac-chan",
        action="store_true",
        help="bắt buộc khi --reset nhắm vào database KHÔNG phải sqlite (Supabase chung)",
    )
    parser.add_argument("--count", type=int, default=140, help="số bản ghi phân loại mô phỏng")
    parser.add_argument(
        "--embed",
        action="store_true",
        help="tính embedding cho kho quy định (cần API key, tốn 1 lệnh gọi cho cả kho)",
    )
    args = parser.parse_args()

    if args.reset:
        url = get_settings().database_url
        if not _cho_phep_reset(url, args.toi_chac_chan):
            print("⛔ TỪ CHỐI — --reset trên database không phải sqlite cần xác nhận rõ.")
            print(f"   Bạn đang định XOÁ SẠCH toàn bộ dữ liệu trên máy chủ: {url.split('@')[-1].split('?')[0]}")
            print("   Nếu chắc chắn, chạy lại với --toi-chac-chan.")
            sys.exit(1)
        print("Xoá sạch cơ sở dữ liệu…")
        reset_database()
    else:
        init_db()

    with session_scope() as session:
        ket_qua = bootstrap(session, demo=args.demo, count=args.count)
        print(
            f"Đã nạp dữ liệu nền: {ket_qua['categories']} nhóm rác, "
            f"{ket_qua['buildings']} toà, {ket_qua['users']} tài khoản."
        )
        if ket_qua["demo_bo_qua"]:
            print("Đã có dữ liệu demo từ trước — bỏ qua. Dùng --reset nếu muốn nạp lại từ đầu.")
        elif ket_qua["demo_da_nap"]:
            print(f"Đã nạp dữ liệu demo mô phỏng ({args.count} lượt phân loại), tất cả gắn cờ is_seed=True.")

        if args.embed:
            from src.services.rag import embed_chunks, so_doan_co_embedding

            them = embed_chunks(session)
            co, tong = so_doan_co_embedding(session)
            if them:
                print(f"Đã nhúng {them} đoạn quy định — {co}/{tong} đoạn có vector, truy hồi chạy hybrid.")
            elif co == tong and tong:
                print(f"Kho quy định đã có sẵn vector ({co}/{tong}).")
            else:
                print(
                    f"KHÔNG nhúng được ({co}/{tong} đoạn có vector). Kiểm EMBEDDING_PROVIDER và API key; "
                    "truy hồi tạm chạy thuần BM25."
                )

    print(f"Xong. Tài khoản demo dùng chung mật khẩu: {DEMO_PASSWORD}")


if __name__ == "__main__":
    main()
