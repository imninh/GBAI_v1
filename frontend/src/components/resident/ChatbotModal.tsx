"use client";

import * as React from "react";
import { Mascot } from "@/components/resident/onboarding";
import { MarkdownContent } from "@/components/ui/markdown";
import { ApiError, api } from "@/lib/api";
import { IconViTri } from "@/lib/icons";
import { Crosshair, Lightbulb, RefreshCw, ScrollText, ThumbsDown, ThumbsUp } from "lucide-react";
import { useSession } from "@/lib/session";
import type { ChatbotResponse } from "@/lib/types";

export function openGreenBinChat() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("open-greenbin-chat"));
  }
}

interface ChatMessage {
  id: string;
  sender: "user" | "ai";
  text: string;
  timestamp: Date;
  responseMeta?: ChatbotResponse;
  feedbackGiven?: number; // 1 | -1
}

interface ChatbotModalProps {
  buildingId?: number | null;
  userLat?: number | null;
  userLng?: number | null;
}

function isBinQuery(text: string): boolean {
  const normalized = text.toLowerCase();
  return (
    normalized.includes("thùng") ||
    normalized.includes("gần") ||
    normalized.includes("chỗ") ||
    normalized.includes("ở đâu") ||
    normalized.includes("vị trí") ||
    normalized.includes("điểm") ||
    normalized.includes("bỏ rác") ||
    normalized.includes("vứt rác") ||
    normalized.includes("tái chế") ||
    normalized.includes("bin")
  );
}

export function ChatbotModal({ buildingId, userLat, userLng }: ChatbotModalProps) {
  const { user, dangXuat } = useSession();
  const [sessionExpired, setSessionExpired] = React.useState(false);
  const [isOpen, setIsOpen] = React.useState(false);
  const [inputQuery, setInputQuery] = React.useState("");
  const [isLoading, setIsLoading] = React.useState(false);
  const [suggestions, setSuggestions] = React.useState<
    { category: string; label: string; question: string }[]
  >([]);
  const [expandedSources, setExpandedSources] = React.useState<Record<string, boolean>>({});
  // Bong bóng chào Bini — hiện một lần (lưu localStorage), tắt khi bấm hoặc hết giờ.
  const [hienBongBong, setHienBongBong] = React.useState(false);

  // Lưu cờ và toạ độ tracking duy nhất 1 lần
  const hasTrackedRef = React.useRef(false);
  const locationRef = React.useRef<{ lat: number; lng: number } | null>(
    userLat && userLng ? { lat: userLat, lng: userLng } : null
  );

  const [gpsStatus, setGpsStatus] = React.useState<"idle" | "tracking" | "located" | "fallback">("idle");
  const [userLocation, setUserLocation] = React.useState<{ lat: number; lng: number } | null>(
    userLat && userLng ? { lat: userLat, lng: userLng } : null
  );

  React.useEffect(() => {
    try {
      if (!window.localStorage.getItem("gbini_greeted")) setHienBongBong(true);
    } catch {
      /* localStorage không dùng được (incognito) → vẫn hiện bong bóng */
    }
    const t = window.setTimeout(() => setHienBongBong(false), 6000);
    return () => window.clearTimeout(t);
  }, []);

  /** Tracking vị trí GPS người dùng DUY NHẤT 1 LẦN khi tra cứu thùng rác */
  const trackLocationOnce = React.useCallback(
    async (forceRefresh = false): Promise<{ lat: number; lng: number } | null> => {
      // Nếu đã tracking 1 lần rồi và không ép đo lại thì tái sử dụng toạ độ
      if (!forceRefresh && hasTrackedRef.current && locationRef.current) {
        return locationRef.current;
      }

      if (typeof window === "undefined" || !("geolocation" in navigator)) {
        setGpsStatus("fallback");
        const fallback = locationRef.current || (userLat && userLng ? { lat: userLat, lng: userLng } : null);
        return fallback;
      }

      setGpsStatus("tracking");
      try {
        const pos = await new Promise<GeolocationPosition>((resolve, reject) => {
          navigator.geolocation.getCurrentPosition(resolve, reject, {
            enableHighAccuracy: true,
            timeout: 5000,
            maximumAge: 60000,
          });
        });
        const coords = { lat: pos.coords.latitude, lng: pos.coords.longitude };
        hasTrackedRef.current = true;
        locationRef.current = coords;
        setUserLocation(coords);
        setGpsStatus("located");
        return coords;
      } catch (err) {
        console.warn("GPS tracking denied or timed out, fallback to building coords:", err);
        hasTrackedRef.current = true;
        setGpsStatus("fallback");
        const fallback = locationRef.current || (userLat && userLng ? { lat: userLat, lng: userLng } : null);
        return fallback;
      }
    },
    [userLat, userLng]
  );

  const [messages, setMessages] = React.useState<ChatMessage[]>([
    {
      id: "welcome",
      sender: "ai",
      text: "Xin chào! Mình là Trợ lý GreenBin AI. Mình có thể giúp bạn:\n• Tra cứu **Luật & Mức phạt** phân loại rác\n• **Tracking GPS & Tìm thùng rác còn chỗ** gần nhất\n• Hướng dẫn **sử dụng các tính năng** của app",
      timestamp: new Date(),
    },
  ]);

  const messagesEndRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    // Tải danh sách gợi ý câu hỏi khi mount
    api
      .chatbotSuggestions()
      .then((res) => {
        if (res?.suggestions) setSuggestions(res.suggestions);
      })
      .catch(() => {});
  }, []);

  React.useEffect(() => {
    // Lắng nghe sự kiện mở chat khi bấm vào con vật Bini
    const handleOpen = () => {
      setIsOpen(true);
      setHienBongBong(false);
      try {
        window.localStorage.setItem("gbini_greeted", "1");
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("open-greenbin-chat", handleOpen);
    return () => window.removeEventListener("open-greenbin-chat", handleOpen);
  }, []);

  React.useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, isOpen]);

  const handleSend = async (queryToSend?: string) => {
    const q = (queryToSend || inputQuery).trim();
    if (!q || isLoading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      sender: "user",
      text: q,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputQuery("");
    setIsLoading(true);

    try {
      // CHỈ tracking GPS duy nhất 1 lần khi người dùng tìm kiếm thùng rác
      let loc = locationRef.current;
      if (isBinQuery(q) && !hasTrackedRef.current) {
        loc = await trackLocationOnce();
      }

      const res = await api.chatbotAsk({
        question: q,
        building_id: buildingId,
        lat: loc?.lat ?? userLat,
        lng: loc?.lng ?? userLng,
      });

      const aiMsg: ChatMessage = {
        id: `ai-${Date.now()}`,
        sender: "ai",
        text: res.answer,
        timestamp: new Date(),
        responseMeta: res,
      };

      setMessages((prev) => [...prev, aiMsg]);
    } catch (err: unknown) {
      const isAuthError = err instanceof ApiError && err.status === 401;
      if (isAuthError) setSessionExpired(true);
      const errorMsg: ChatMessage = {
        id: `error-${Date.now()}`,
        sender: "ai",
        text: isAuthError
          ? "Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại."
          : (err instanceof Error ? err.message : null) || "Rất tiếc, đã có lỗi kết nối tới máy chủ AI. Bạn thử lại nhé!",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleFeedback = async (msgId: string, rating: number) => {
    const msg = messages.find((m) => m.id === msgId);
    if (!msg || !msg.responseMeta) return;

    try {
      await api.chatbotFeedback({
        question: messages[messages.indexOf(msg) - 1]?.text || "",
        answer: msg.text,
        intent: msg.responseMeta.intent,
        rating,
      });

      setMessages((prev) =>
        prev.map((m) => (m.id === msgId ? { ...m, feedbackGiven: rating } : m))
      );
    } catch {
      // Bỏ qua lỗi feedback
    }
  };

  const toggleSources = (msgId: string) => {
    setExpandedSources((prev) => ({
      ...prev,
      [msgId]: !prev[msgId],
    }));
  };

  // §6.1 & §6.2: Chưa đăng nhập hoặc token hết hạn (401) → cửa chặn, không rơi vào ngõ cụt.
  if (!user || sessionExpired) {
    return (
      <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
        <div className="w-full max-w-sm rounded-2xl bg-surface p-6 text-center shadow-2xl dark:bg-zinc-900 dark:text-zinc-100">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-leaf-dark/90 text-white">
            <Mascot size={48} tuThe="hello" className="animate-gbbreath" />
          </div>
          <h3 className="font-bold text-base">Cần đăng nhập để dùng trợ lý</h3>
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            Trợ lý GreenBin AI chỉ dành cho cư dân đã đăng nhập. Vui lòng đăng nhập để tiếp tục hỏi đáp luật, thùng rác và hướng dẫn app.
          </p>
          <button
            type="button"
            onClick={() => dangXuat()}
            className="mt-5 w-full rounded-xl bg-leaf px-4 py-2.5 font-medium text-white shadow-xs transition-colors hover:bg-leaf-dark cursor-pointer"
          >
            Đăng nhập lại
          </button>
        </div>
      </div>
    );
  }

  return (
    <>
      {/* Nút tròn mặt Bini nổi (thay pill) + bong bóng chào một lần */}
      {!isOpen && (
        <div className="fixed bottom-20 right-4 z-[1001] flex items-end gap-2.5 sm:bottom-6 sm:right-6">
          {hienBongBong && (
            <div className="gbchatgreet pointer-events-none relative mb-6 max-w-[228px] rounded-2xl border border-line bg-surface px-3.5 py-2.5 text-[12.5px] font-semibold leading-snug text-ink shadow-[0_10px_28px_-8px_rgba(28,66,41,.35)]">
              Chào bạn, mình là Bini — hỏi mình cách phân loại rác nhé 👋
              <span className="absolute -bottom-1.5 right-7 h-3 w-3 rotate-45 border-b border-r border-line bg-surface" />
            </div>
          )}
          <button
            onClick={() => {
              setIsOpen(true);
              setHienBongBong(false);
              try {
                window.localStorage.setItem("gbini_greeted", "1");
              } catch {
                /* ignore */
              }
            }}
            className="relative flex h-16 w-16 items-center justify-center rounded-full bg-leaf-dark shadow-[0_10px_30px_-6px_rgba(28,66,41,.45)] ring-2 ring-leaf-mint/60 transition-transform duration-300 hover:scale-105 active:scale-95"
            title="Bấm vào để hỏi Bini AI"
            aria-label="Mở trợ lý Bini"
          >
            <span className="-mt-1 flex h-[72px] w-[72px] items-center justify-center overflow-visible">
              <Mascot size={58} tuThe="hello" className="drop-shadow-[0_4px_8px_rgba(0,0,0,.25)]" />
            </span>
            <span className="absolute top-1 right-1 flex h-3 w-3">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-leaf-mint opacity-75"></span>
              <span className="relative inline-flex h-3 w-3 rounded-full bg-leaf-mint"></span>
            </span>
          </button>
        </div>
      )}

      {/* Cửa sổ Chat Modal */}
      {isOpen && (
        <div className="fixed inset-0 z-[9999] flex items-end justify-center bg-black/40 backdrop-blur-xs p-0 sm:items-center sm:p-4">
          <div className="flex h-[92vh] w-full max-w-lg flex-col rounded-t-2xl bg-surface shadow-2xl sm:h-[650px] sm:rounded-2xl dark:bg-zinc-900 dark:text-zinc-100">
            {/* Header với Bini avatar */}
            <div className="flex items-center justify-between border-b border-leaf-dark/40 bg-gradient-to-r from-leaf-dark to-leaf px-4 py-3 text-white rounded-t-2xl">
              <div className="flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-full bg-leaf-dark/90 border border-leaf-mint/40 overflow-hidden shadow-md">
                  <Mascot size={42} tuThe="hello" className="animate-gbbreath" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-sm">Bini — Trợ lý AI GreenBin</h3>
                    <span className="rounded-full bg-leaf-dark/80 px-2 py-0.5 text-[10px] font-medium text-leaf-mint border border-leaf/30">
                      Mistral AI
                    </span>
                  </div>
                  <p className="text-xs text-leaf-mint/90">
                    Luật rác · Thùng rác gần nhất · Hướng dẫn app
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="rounded-full p-2 text-leaf-mint hover:bg-leaf-dark hover:text-white transition-colors"
                aria-label="Đóng"
              >
                ✕
              </button>
            </div>

            {/* Thanh hiển thị trạng thái GPS Tracking thời gian thực */}
            <div className="flex items-center justify-between border-b border-leaf-dark/15 bg-leaf-soft/90 px-3.5 py-1.5 text-[11px] text-leaf-dark dark:bg-leaf-dark/50 dark:text-leaf-mint">
              <div className="flex items-center gap-1.5 overflow-hidden">
                {gpsStatus === "tracking" ? (
                  <>
                    <span className="relative flex h-2 w-2">
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-leaf-mint opacity-75"></span>
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-leaf-mint"></span>
                    </span>
                    <span className="font-medium animate-pulse text-leaf-dark dark:text-leaf-mint">
                      Đang tracking vị trí GPS của bạn...
                    </span>
                  </>
                ) : gpsStatus === "located" && userLocation ? (
                  <>
                    <Crosshair className="h-4 w-4 text-leaf" strokeWidth={1.9} />
                    <span className="truncate font-medium">
                      GPS: {userLocation.lat.toFixed(4)}°N, {userLocation.lng.toFixed(4)}°E (Chính xác cao)
                    </span>
                  </>
                ) : (
                  <>
                    <IconViTri className="h-4 w-4 shrink-0 text-zinc-500" strokeWidth={1.9} />
                    <span className="truncate text-zinc-600 dark:text-zinc-400">
                      Vị trí: Toà nhà {userLat ? `(${userLat.toFixed(4)}, ${userLng?.toFixed(4)})` : "mặc định"}
                    </span>
                  </>
                )}
              </div>
              <button
                type="button"
                onClick={() => void trackLocationOnce(true)}
                disabled={gpsStatus === "tracking"}
                className="shrink-0 rounded-md bg-leaf-soft/80 px-2 py-0.5 font-semibold text-leaf-dark hover:bg-leaf-soft active:scale-95 disabled:opacity-50 dark:bg-leaf-dark/60 dark:text-leaf-mint cursor-pointer"
                title="Bấm để tracking lại toạ độ GPS"
              >
                {gpsStatus === "tracking" ? "Đang đo..." : (<><RefreshCw className="mr-1.5 inline h-4 w-4" strokeWidth={1.9} />Cập nhật GPS</>)}
              </button>
            </div>

            {/* Gợi ý câu hỏi nhanh */}
            {suggestions.length > 0 && messages.length <= 2 && (
              <div className="border-b border-zinc-100 bg-zinc-50 p-2 dark:border-zinc-800 dark:bg-zinc-950">
                <p className="mb-1.5 flex items-center gap-1 px-1 text-[11px] font-medium text-zinc-500">
                  <Lightbulb className="h-3.5 w-3.5" strokeWidth={1.9} /> Câu hỏi gợi ý:
                </p>
                <div className="flex gap-1.5 overflow-x-auto pb-1 text-xs">
                  {suggestions.map((s, idx) => (
                    <button
                      key={idx}
                      onClick={() => handleSend(s.question)}
                      className="shrink-0 rounded-full border border-leaf-soft bg-surface px-3 py-1 text-leaf-dark shadow-xs hover:bg-leaf-soft active:scale-95 dark:border-leaf-dark dark:bg-zinc-900 dark:text-leaf-mint"
                    >
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Danh sách Tin nhắn */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
              {messages.map((m) => (
                <div
                  key={m.id}
                  className={`flex flex-col ${
                    m.sender === "user" ? "items-end" : "items-start"
                  }`}
                >
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-2.5 ${
                      m.sender === "user"
                        ? "bg-leaf text-white rounded-br-xs"
                        : "bg-zinc-100 text-zinc-900 rounded-bl-xs dark:bg-zinc-800 dark:text-zinc-100"
                    }`}
                  >
                    {/* Badge nguồn và Confidence (cho AI) */}
                    {m.sender === "ai" && m.responseMeta && (
                      <div className="mb-1.5 flex flex-wrap items-center gap-1.5 text-[11px]">
                        <span className="rounded-md bg-leaf-soft px-1.5 py-0.5 font-medium text-leaf-dark dark:bg-leaf-dark dark:text-leaf-mint">
                          {m.responseMeta.source_badge}
                        </span>
                        <span
                          className={`rounded-md px-1.5 py-0.5 font-medium ${
                            m.responseMeta.confidence_level === "High"
                              ? "bg-blue-100 text-blue-800 dark:bg-blue-950 dark:text-blue-300"
                              : m.responseMeta.confidence_level === "Medium"
                              ? "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300"
                              : "bg-zinc-200 text-zinc-700 dark:bg-zinc-700 dark:text-zinc-300"
                          }`}
                        >
                          Độ tin cậy: {m.responseMeta.confidence_level}
                        </span>
                      </div>
                    )}

                    {/* Nội dung tin nhắn */}
                    <MarkdownContent content={m.text} />

                    {/* Danh sách thùng rác khả thi (nếu có) */}
                    {m.responseMeta?.viable_bins &&
                      m.responseMeta.viable_bins.length > 0 && (
                        <div className="mt-3 space-y-2 border-t border-zinc-200 pt-2 dark:border-zinc-700">
                          <p className="text-xs font-semibold text-leaf-dark dark:text-leaf-mint flex items-center justify-between">
                            <span className="flex items-center gap-1"><IconViTri className="h-3.5 w-3.5" strokeWidth={1.9} />Thùng rác khả dụng gần bạn (GPS Tracking):</span>
                            <span className="text-[10px] font-normal text-zinc-500 dark:text-zinc-400">
                              Đã so khớp khoảng cách
                            </span>
                          </p>
                          {m.responseMeta.viable_bins.map((bin) => (
                            <div
                              key={bin.id}
                              className="rounded-lg border border-zinc-200 bg-surface p-2.5 text-xs shadow-xs dark:border-zinc-700 dark:bg-zinc-900"
                            >
                              <div className="flex justify-between font-medium">
                                <span className="font-bold text-zinc-800 dark:text-zinc-200">{bin.name}</span>
                                <span
                                  className={
                                    bin.fill_percent < 70
                                      ? "text-leaf font-bold"
                                      : "text-amber-600 font-bold"
                                  }
                                >
                                  Đầy: {bin.fill_percent}%
                                </span>
                              </div>
                              <div className="text-zinc-500 dark:text-zinc-400 mt-1 flex items-center justify-between">
                                <span className="truncate pr-2">{bin.address}</span>
                                {bin.distance_meters !== null && (
                                  <span className="shrink-0 font-semibold text-leaf-dark dark:text-leaf-mint bg-leaf-soft/80 dark:bg-leaf-dark px-1.5 py-0.5 rounded border border-leaf-mint/40">
                                    Cách ~{Math.round(bin.distance_meters)}m
                                  </span>
                                )}
                              </div>
                              <div className="mt-1.5 flex flex-wrap gap-1">
                                {bin.category_names?.map((c, i) => (
                                  <span
                                    key={i}
                                    className="rounded bg-zinc-100 px-1 py-0.5 text-[10px] text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
                                  >
                                    {c}
                                  </span>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}

                    {/* Nguồn trích dẫn (Evidence Chips) */}
                    {m.responseMeta?.sources &&
                      m.responseMeta.sources.length > 0 && (
                        <div className="mt-2.5 border-t border-zinc-200/60 pt-1.5 dark:border-zinc-700/60">
                          <button
                            onClick={() => toggleSources(m.id)}
                            className="text-[11px] font-semibold text-leaf-dark underline hover:text-leaf-dark dark:text-leaf-mint"
                          >
                            {expandedSources[m.id]
                              ? "Ẩn căn cứ trích dẫn ▲"
                              : `Xem ${m.responseMeta.sources.length} căn cứ trích dẫn ▼`}
                          </button>

                          {expandedSources[m.id] && (
                            <div className="mt-1.5 space-y-1.5">
                              {m.responseMeta.sources.map((s, idx) => (
                                <div
                                  key={idx}
                                  className="rounded bg-surface/80 p-2 text-[11px] text-zinc-700 shadow-2xs dark:bg-zinc-900/90 dark:text-zinc-300 border border-zinc-200/50 dark:border-zinc-700/50"
                                >
                                  <div className="flex items-center gap-1 font-semibold text-leaf-dark dark:text-leaf-mint">
                                    <ScrollText className="h-3.5 w-3.5 shrink-0" strokeWidth={1.9} />
                                    {s.doc_title} · {s.section}
                                  </div>
                                  <div className="mt-0.5 italic text-zinc-600 dark:text-zinc-400">
                                    &ldquo;{s.quote}&rdquo;
                                  </div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}

                    {/* Phản hồi 👍 / 👎 (HAX G15) */}
                    {m.sender === "ai" && m.responseMeta && (
                      <div className="mt-2 flex items-center justify-end gap-2 border-t border-zinc-200/40 pt-1 text-[11px] text-zinc-500 dark:border-zinc-700/40">
                        <span>Câu trả lời có hữu ích?</span>
                        <button
                          onClick={() => handleFeedback(m.id, 1)}
                          disabled={m.feedbackGiven !== undefined}
                          className={`rounded p-1 transition-colors ${
                            m.feedbackGiven === 1
                              ? "bg-leaf-soft text-leaf-dark font-bold"
                              : "hover:bg-zinc-200 dark:hover:bg-zinc-700"
                          }`}
                          title="Hữu ích"
                        >
                          <ThumbsUp className="h-4 w-4" strokeWidth={2} />
                        </button>
                        <button
                          onClick={() => handleFeedback(m.id, -1)}
                          disabled={m.feedbackGiven !== undefined}
                          className={`rounded p-1 transition-colors ${
                            m.feedbackGiven === -1
                              ? "bg-red-200 text-red-900 font-bold"
                              : "hover:bg-zinc-200 dark:hover:bg-zinc-700"
                          }`}
                          title="Chưa hữu ích"
                        >
                          <ThumbsDown className="h-4 w-4" strokeWidth={2} />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {isLoading && (
                <div className="flex items-center gap-2 text-xs text-zinc-500">
                  <div className="flex h-6 w-6 animate-spin items-center justify-center rounded-full border-2 border-leaf border-t-transparent"></div>
                  <span>Trợ lý AI đang tra cứu quy định và dữ liệu...</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Khung Nhập Liệu */}
            <div className="border-t border-zinc-200 p-3 dark:border-zinc-800 bg-surface dark:bg-zinc-900 rounded-b-2xl">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  handleSend();
                }}
                className="flex gap-2"
              >
                <input
                  id="chatbot-input"
                  type="text"
                  value={inputQuery}
                  onChange={(e) => setInputQuery(e.target.value)}
                  placeholder="Hỏi về mức phạt, thùng rác, cách dùng app..."
                  className="flex-1 rounded-xl border border-zinc-300 px-3.5 py-2.5 text-sm focus:border-leaf focus:outline-none dark:border-zinc-700 dark:bg-zinc-800"
                  disabled={isLoading}
                />
                <button
                  id="chatbot-send-btn"
                  type="submit"
                  disabled={!inputQuery.trim() || isLoading}
                  className="rounded-xl bg-leaf px-4 py-2.5 font-medium text-white shadow-xs transition-colors hover:bg-leaf-dark disabled:opacity-50 cursor-pointer"
                >
                  Gửi
                </button>
              </form>
              <p className="mt-1 text-center text-[10px] text-zinc-400">
                AI tra cứu từ Luật BVMT 2020, NĐ 45 & cảm biến IoT toà nhà.
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
