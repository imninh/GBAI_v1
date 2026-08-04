/**
 * BQL Smart Trash Bin System - Route Optimizer (TSP Solver)
 * Calculates the shortest collection route starting from a Central Depot (Trạm Thu Gom Central),
 * visiting all selected/urgent trash bins, and returning to the processing facility.
 * Uses Nearest-Neighbor heuristic + 2-opt refinement for fast & accurate distance calculation (Haversine formula).
 */

class BQLRouteOptimizer {
  constructor() {
    // Central Collection Depot (Trạm Tập Kết / Hầm B1)
    this.depot = {
      id: "DEPOT-00",
      name: "Trạm Tập Kết Central (Hầm B1)",
      building: "Khu Kỹ Thuật",
      locationDesc: "Hầm B1 - Lối xuất hàng",
      lat: 10.776500,
      lng: 106.700500,
      isDepot: true
    };
  }

  /**
   * Distance between two coordinates in kilometers using Haversine formula
   */
  getDistanceKm(lat1, lon1, lat2, lon2) {
    const R = 6371; // Radius of the earth in km
    const dLat = this.deg2rad(lat2 - lat1);
    const dLon = this.deg2rad(lon2 - lon1);
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(this.deg2rad(lat1)) * Math.cos(this.deg2rad(lat2)) *
      Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
  }

  deg2rad(deg) {
    return deg * (Math.PI / 180);
  }

  /**
   * Optimize collection route starting from Depot through target bins and back to Depot
   * @param {Array} bins - Array of trash bin objects to visit
   * @returns {Object} { route: Array, totalDistanceKm: Number, estimatedMinutes: Number }
   */
  calculateShortestRoute(bins) {
    if (!bins || bins.length === 0) {
      return { route: [], totalDistanceKm: 0, estimatedMinutes: 0 };
    }

    const unvisited = [...bins];
    const route = [this.depot];
    let currentPoint = this.depot;

    // Nearest Neighbor Heuristic
    while (unvisited.length > 0) {
      let nearestIdx = 0;
      let minDistance = Infinity;

      for (let i = 0; i < unvisited.length; i++) {
        const dist = this.getDistanceKm(
          currentPoint.lat, currentPoint.lng,
          unvisited[i].lat, unvisited[i].lng
        );
        if (dist < minDistance) {
          minDistance = dist;
          nearestIdx = i;
        }
      }

      const nextBin = unvisited.splice(nearestIdx, 1)[0];
      route.push(nextBin);
      currentPoint = nextBin;
    }

    // Return to Depot to close the loop
    route.push(this.depot);

    // Apply 2-opt refinement for route smoothing
    const optimizedRoute = this.twoOptRefine(route);

    // Calculate total distance & estimated time
    let totalDist = 0;
    for (let i = 0; i < optimizedRoute.length - 1; i++) {
      totalDist += this.getDistanceKm(
        optimizedRoute[i].lat, optimizedRoute[i].lng,
        optimizedRoute[i + 1].lat, optimizedRoute[i + 1].lng
      );
    }

    // Rough speed assumption: 15km/h collection vehicle speed + 3 mins per bin pickup
    const travelTimeMin = (totalDist / 15) * 60;
    const pickupTimeMin = (bins.length) * 3;
    const estimatedMinutes = Math.round(travelTimeMin + pickupTimeMin);

    return {
      route: optimizedRoute,
      totalDistanceKm: parseFloat(totalDist.toFixed(2)),
      estimatedMinutes: estimatedMinutes,
      binCount: bins.length
    };
  }

  twoOptRefine(route) {
    let bestRoute = [...route];
    let improved = true;
    let iterations = 0;

    while (improved && iterations < 50) {
      improved = false;
      iterations++;

      for (let i = 1; i < bestRoute.length - 2; i++) {
        for (let j = i + 1; j < bestRoute.length - 1; j++) {
          const d1 = this.getDistanceKm(bestRoute[i - 1].lat, bestRoute[i - 1].lng, bestRoute[i].lat, bestRoute[i].lng) +
                     this.getDistanceKm(bestRoute[j].lat, bestRoute[j].lng, bestRoute[j + 1].lat, bestRoute[j + 1].lng);

          const d2 = this.getDistanceKm(bestRoute[i - 1].lat, bestRoute[i - 1].lng, bestRoute[j].lat, bestRoute[j].lng) +
                     this.getDistanceKm(bestRoute[i].lat, bestRoute[i].lng, bestRoute[j + 1].lat, bestRoute[j + 1].lng);

          if (d2 < d1) {
            // Reverse segment between i and j
            const newSegment = bestRoute.slice(i, j + 1).reverse();
            bestRoute.splice(i, j - i + 1, ...newSegment);
            improved = true;
          }
        }
      }
    }

    return bestRoute;
  }
}

window.BQLRouteOptimizer = BQLRouteOptimizer;
