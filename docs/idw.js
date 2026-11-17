/* IDW in metres (EPSG:32647), p=2, up to 12 nearest neighbours. */
(function (root) {
  "use strict";
  function interpolate(points, targets) {
    const unique = new Map();
    for (const p of points) {
      if ([p.x, p.y, p.value].every(Number.isFinite)) unique.set(`${p.x},${p.y}`, p);
    }
    const source = [...unique.values()];
    if (source.length < 3) return {status: "insufficient", values: []};
    const a = source[0], b = source[1];
    const baseline = Math.hypot(b.x - a.x, b.y - a.y);
    // Three distinct points must span an area, rather than a single line.
    if (!source.some(p => Math.abs((b.x-a.x)*(p.y-a.y)-(b.y-a.y)*(p.x-a.x)) / baseline > 1)) {
      return {status: "insufficient", values: []};
    }
    const values = targets.map(t => {
      const neighbours = source.map(p => ({p, d2: (p.x-t.x)**2 + (p.y-t.y)**2}))
        .sort((a,b) => a.d2-b.d2).slice(0,12);
      if (neighbours[0].d2 < 1e-6) return {id:t.id, value:neighbours[0].p.value, distance:0, neighbours:1};
      // Relative weights avoid large intermediate numbers at short distances.
      let sum = 0, weight = 0;
      for (const n of neighbours) { const w=neighbours[0].d2/n.d2; sum+=w*n.p.value; weight+=w; }
      return {id:t.id, value:sum/weight, distance:Math.sqrt(neighbours[0].d2), neighbours:neighbours.length};
    });
    return {status:"available", values};
  }
  const api = {interpolate};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.KKIDW = api;
})(typeof window !== "undefined" ? window : this);
