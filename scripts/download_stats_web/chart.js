/* Calendar aggregation is pure and shared by browser controls and Node test fixtures. */
"use strict";
(() => {
  const DAY = 86400000;
  const keys = ["historical", "observed", "gap"];
  const parse = value => new Date(`${value}T00:00:00Z`);
  const iso = date => date.toISOString().slice(0, 10);
  function bounds(value, grain) {
    const start = parse(value);
    if (grain === "week") start.setUTCDate(start.getUTCDate() - (start.getUTCDay() + 6) % 7);
    if (grain === "month") start.setUTCDate(1);
    if (grain === "year") start.setUTCMonth(0, 1);
    const end = new Date(start);
    if (grain === "month") end.setUTCMonth(end.getUTCMonth() + 1);
    else if (grain === "year") end.setUTCFullYear(end.getUTCFullYear() + 1);
    else end.setUTCDate(end.getUTCDate() + (grain === "week" ? 7 : 1));
    return [iso(start), iso(new Date(end.getTime() - DAY))];
  }
  function selectRange(days, range) {
    if (!days.length || range === "all") return days;
    const earliest = iso(new Date(parse(days.at(-1).date).getTime() - (Number(range) - 1) * DAY));
    return days.filter(day => day.date >= earliest);
  }
  function aggregate(days, grain) {
    const groups = new Map();
    for (const day of days) {
      const [start, end] = bounds(day.date, grain);
      if (!groups.has(start)) groups.set(start, {start, end, first: day.date, last: day.date,
        historical: 0, observed: 0, gap: 0, partial: false, windows: new Map()});
      const group = groups.get(start);
      for (const key of keys) group[key] += day[key];
      group.last = day.date;
      group.partial ||= day.partial;
      for (const window of day.windows) group.windows.set(JSON.stringify(window), window);
    }
    return [...groups.values()].map(group => ({...group,
      partial: group.partial || group.first !== group.start || group.last !== group.end,
      total: keys.reduce((sum, key) => sum + group[key], 0),
      windows: [...group.windows.values()]}));
  }
  globalThis.DownloadChart = {aggregate, selectRange, bounds};
  if (typeof document === "undefined") return;

  const data = globalThis.DOWNLOAD_DATA;
  const catalogs = globalThis.DOWNLOAD_MESSAGES;
  const get = id => document.getElementById(id);
  const svg = get("chart"), tooltip = get("tooltip"), container = get("chart-container");
  const preferred = navigator.language.toLowerCase().split("-")[0];
  let language = Object.hasOwn(catalogs, preferred) ? preferred : "en";
  let active = 0;
  const t = key => catalogs[language][key];
  const number = value => new Intl.NumberFormat(language, {maximumFractionDigits: 6}).format(value);
  const ns = "http://www.w3.org/2000/svg";
  function element(tag, attributes, text) {
    const node = document.createElementNS(ns, tag);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function description(group) {
    const lines = [`${group.first} – ${group.last} (UTC)`, `${t("title")}: ${number(group.total)}`];
    for (const key of keys) lines.push(`${t(key)}: ${number(group[key])}`);
    if (group.partial) lines.push(t("partial"));
    if (group.windows.length) {
      lines.push(t("windows"));
      if (group.windows.length <= 3) {
        for (const window of group.windows) lines.push(`${window.from} → ${window.to} · ${t(window.kind)}`);
      } else {
        const from = group.windows.map(window => window.from).sort()[0];
        const to = group.windows.map(window => window.to).sort().at(-1);
        lines.push(`${from} → ${to}`);
        lines.push(`${number(group.windows.length)} · ${[...new Set(group.windows.map(window => t(window.kind)))].join(', ')}`);
      }
    }
    return lines.join("\n");
  }
  function show(group, node) {
    tooltip.textContent = description(group);
    tooltip.hidden = false;
    const box = node.getBoundingClientRect(), parent = container.getBoundingClientRect();
    tooltip.style.left = `${Math.max(0, Math.min(box.left - parent.left, parent.width - tooltip.offsetWidth))}px`;
    tooltip.style.top = `${Math.max(0, box.top - parent.top - tooltip.offsetHeight - 8)}px`;
  }
  function niceMaximum(value) {
    if (value <= 1) return 1;
    const scale = 10 ** Math.floor(Math.log10(value));
    return Math.ceil(value / scale / .5) * .5 * scale;
  }
  function render() {
    tooltip.hidden = true;
    const days = selectRange(data.days, get("range").value);
    const groups = aggregate(days, get("aggregation").value);
    get("total").textContent = number(groups.reduce((sum, group) => sum + group.total, 0));
    get("selection").textContent = days.length ? `${days[0].date} – ${days.at(-1).date} · UTC` : "";
    get("empty").hidden = !!groups.length;
    svg.replaceChildren();
    svg.setAttribute("aria-label", t("title"));
    svg.append(element("title", {}, t("title")));
    const canvasWidth = Math.max(300, container.clientWidth);
    svg.setAttribute("viewBox", `0 0 ${canvasWidth} 350`);
    const left = 48, top = 12, width = canvasWidth - left - 14, height = 280;
    const maximum = niceMaximum(Math.max(0, ...groups.map(group => group.total)));
    for (let tick = 0; tick <= 4; tick++) {
      const y = top + height - height * tick / 4;
      svg.append(element("path", {class: "grid", d: `M${left} ${y}h${width}`}));
      svg.append(element("text", {x: left - 10, y: y + 4, "text-anchor": "end"}, number(maximum * tick / 4)));
    }
    const step = width / Math.max(1, groups.length);
    active = Math.min(active, Math.max(0, groups.length - 1));
    groups.forEach((group, index) => {
      const x = left + index * step;
      const node = element("g", {class: "bar", tabindex: index === active ? "0" : "-1",
        role: "img", "aria-label": description(group)});
      node.append(element("title", {}, description(group)));
      node.append(element("rect", {class: "hit", x, y: top, width: step, height,
        fill: "transparent"}));
      let y = top + height;
      for (const key of keys) {
        const h = group[key] / maximum * height;
        y -= h;
        node.append(element("rect", {class: `${key}-fill`, x: x + step * .1, y,
          width: step * .8, height: h, "pointer-events": "none"}));
      }
      node.addEventListener("pointerenter", () => show(group, node));
      node.addEventListener("pointerleave", () => { tooltip.hidden = true; });
      node.addEventListener("focus", () => {
        svg.querySelectorAll(".bar").forEach(bar => bar.setAttribute("tabindex", "-1"));
        node.setAttribute("tabindex", "0");
        active = index; show(group, node);
      });
      node.addEventListener("blur", () => { tooltip.hidden = true; });
      node.addEventListener("keydown", event => {
        const moves = {ArrowLeft: Math.max(0, index - 1), ArrowRight: Math.min(groups.length - 1, index + 1),
          Home: 0, End: groups.length - 1};
        if (event.key in moves) { event.preventDefault(); svg.querySelectorAll(".bar")[moves[event.key]].focus(); }
        if (event.key === "Escape") tooltip.hidden = true;
      });
      svg.append(node);
      // Label at most seven positions, with whole bucket dates in the tooltip.
      const labelCount = Math.max(1, Math.floor(width / 150));
      if (index % Math.max(1, Math.ceil(groups.length / labelCount)) === 0 || index === groups.length - 1) {
        const anchor = index === 0 ? "start" : index === groups.length - 1 ? "end" : "middle";
        const label = get("aggregation").value === "year" ? group.start.slice(0, 4)
          : get("aggregation").value === "month" ? group.start.slice(0, 7) : group.first;
        svg.append(element("text", {x: x + step / 2, y: 321, "text-anchor": anchor}, label));
      }
    });
  }
  function translate() {
    document.documentElement.lang = language;
    document.title = `${t("title")} · Open Garden Planner`;
    document.querySelectorAll("[data-i18n]").forEach(node => { node.textContent = t(node.dataset.i18n); });
    get("stamps").textContent = `${t("updated")}: ${data.updated_at} · ${t("baseline")}: ${data.baseline_at}`;
    render();
  }
  get("source").href = `https://github.com/${data.repo}/blob/download-stats/SUMMARY.md`;
  get("language").value = language;
  get("language").addEventListener("change", event => { language = event.target.value; translate(); });
  get("theme").addEventListener("change", event => { document.documentElement.dataset.theme = event.target.value; });
  get("aggregation").addEventListener("change", render);
  get("range").addEventListener("change", render);
  window.addEventListener("resize", render);
  translate();
})();
