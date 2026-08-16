"use client";

/** Bản đồ tuyến thu gom cho Ban quản lý — vẽ toạ độ thật từ OSRM + live tracking xe. */

import type { LoTrinhMeta, RouteStop } from "@/lib/types";
import RouteMapBase, { type ToaDoDuongDi } from "@/components/map/route-map-base";
import LiveVehicleMarker from "@/components/map/live-vehicle-marker";

export default function RouteMap({
  stops,
  duong_di,
  lo_trinh_meta,
  route_id,
}: {
  stops: RouteStop[];
  duong_di?: ToaDoDuongDi[] | null;
  lo_trinh_meta?: LoTrinhMeta | null;
  route_id?: number | null;
}) {
  return (
    <RouteMapBase
      stops={stops}
      duong_di={duong_di}
      lo_trinh_meta={lo_trinh_meta}
      showLegend={true}
      className="h-full w-full"
    >
      {route_id != null && <LiveVehicleMarker routeId={route_id} />}
    </RouteMapBase>
  );
}

