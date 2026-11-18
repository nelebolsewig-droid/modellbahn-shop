/**
 * Drives the scroll film of the start page: reads how far each chapter has been scrolled
 * and moves the pieces on its pinned stage. Plain DOM work on purpose, outside React:
 * it runs on every animation frame while scrolling and must not re-render anything.
 */

const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));
const lerp = (from: number, to: number, t: number) => from + (to - from) * t;
const ease = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2);
const span = (p: number, from: number, to: number) => clamp((p - from) / (to - from), 0, 1);
const decimal = (value: number, digits: number) => value.toFixed(digits).replace(".", ",");

/** Denominators of the gauges the crane shrinks through: 0, H0, TT, N. */
const SCALES = [45, 87, 120, 160] as const;
/** Height of the EDK 6 with its jib in H0 (1:87), in millimetres. */
const HEIGHT_H0_MM = 188.4;
const RULER_TOP_MM = (HEIGHT_H0_MM * 87) / 45;
const PHONE_WIDTH = 820;

/** How far a pinned chapter has been scrolled through, 0 to 1. */
function progress(element: HTMLElement): number {
  const rect = element.getBoundingClientRect();
  const room = rect.height - window.innerHeight;
  return room <= 0 ? clamp(-rect.top / Math.max(1, rect.height), 0, 1) : clamp(-rect.top / room, 0, 1);
}

/**
 * Starts the film inside `root` and returns a function that stops it. With reduced
 * motion nothing is animated: the chapters are laid out as still, complete pages.
 */
export function startFilm(root: HTMLElement): () => void {
  const one = (name: string) => {
    const element = root.querySelector<HTMLElement>(`[data-film="${name}"]`);
    if (!element) {
      throw new Error(`scroll film: [data-film="${name}"] is missing`);
    }
    return element;
  };
  const all = (selector: string) => [...root.querySelectorAll<HTMLElement>(selector)];

  const layers = all(".layer");
  const calls = all(".call");
  const items = [...one("partList").children];
  const gauge = [...one("gauge").children];
  const numerals = all(".panel .no");
  const rising = all(".rise");

  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    root.classList.add("film-still");
    for (const item of items) item.classList.add("on");
    gauge[1]?.classList.add("on");
    one("ratio").textContent = "1:87";
    one("mm").textContent = `${decimal(HEIGHT_H0_MM, 1)} mm`;
    return () => root.classList.remove("film-still");
  }

  root.classList.add("film-js");
  let pxPerMm = 1;

  /** The ruler: the crane in gauge 0 fills 92 % of the bench height. */
  function drawRuler() {
    const ruler = one("ruler");
    pxPerMm = (one("bench").clientHeight * 0.92) / RULER_TOP_MM;
    ruler.style.setProperty("--tick", `${pxPerMm * 10}px`);
    ruler.replaceChildren(
      ...Array.from({ length: 8 }, (_, index) => {
        const label = document.createElement("span");
        label.textContent = String(index * 50);
        label.style.bottom = `${index * 50 * pxPerMm}px`;
        return label;
      }),
    );
  }

  function frame() {
    const viewport = window.innerHeight;
    const total = document.documentElement.scrollHeight - viewport;
    const filmRect = root.getBoundingClientRect();
    const inFilm = filmRect.top < viewport * 0.5 && filmRect.bottom > viewport * 0.5;
    const bar = one("progress");
    bar.style.opacity = inFilm ? "1" : "0";
    bar.style.transform = `scaleX(${total > 0 ? clamp(window.scrollY / total, 0, 1) : 0})`;

    // 1 · Auftakt: the word spreads and sinks, the crane grows, then the dimension lines draw.
    const p1 = progress(one("auftakt"));
    const grow = ease(span(p1, 0, 0.62));
    const word = one("word");
    word.style.transform = `translateY(${lerp(-62, -20, grow)}%) scale(${lerp(1, 1.9, grow)})`;
    word.style.letterSpacing = `${lerp(-0.07, 0.22, grow)}em`;
    word.style.opacity = String(1 - span(p1, 0.34, 0.6));
    const grown = window.innerWidth < PHONE_WIDTH ? 0.98 : 1.34;
    one("heroCrane").style.transform = `translateY(${lerp(2, -3, grow)}vh) scale(${lerp(0.8, grown, grow)})`;
    for (const [index, call] of calls.entries()) {
      const t = span(p1, 0.56 + index * 0.1, 0.7 + index * 0.1);
      const hidden = 100 - t * 104;
      call.style.opacity = String(t);
      call.style.clipPath = call.classList.contains("to-r")
        ? `inset(-60px ${hidden}% -10px -10px)`
        : `inset(-60px -10px -10px ${hidden}%)`;
    }
    const copy = one("heroCopy");
    const copyGone = span(p1, 0.08, 0.3);
    copy.style.transform = `translateY(${lerp(0, -70, span(p1, 0, 0.35))}px)`;
    copy.style.opacity = String(1 - copyGone);
    // A faded-out button must not be clickable or reachable by keyboard.
    copy.toggleAttribute("inert", copyGone >= 1);
    one("hint").style.opacity = String(1 - span(p1, 0, 0.08));

    // 2 · Zerlegen: one assembly after the other leaves the crane.
    const p2 = progress(one("zerlegen"));
    const swap = span(p2, 0.02, 0.08);
    one("whole").style.opacity = String(1 - swap);
    const base = one("base");
    base.style.opacity = String(swap);
    const glow = one("glow");
    glow.style.opacity = String(span(p2, 0.05, 0.5));
    glow.style.transform = `translate(-50%, -50%) scale(${lerp(0.6, 1.15, span(p2, 0.05, 0.9))})`;
    one("kit").style.transform = `scale(${lerp(1, 0.9, span(p2, 0.1, 0.9))})`;
    let loose = 0;
    for (const [index, layer] of layers.entries()) {
      const order = layers.length - 1 - index; // the top assemblies leave first
      const t = ease(span(p2, 0.1 + order * 0.105, 0.3 + order * 0.105));
      if (t > 0.5) loose += 1;
      const { x = "0", y = "0", r = "0" } = layer.dataset;
      layer.style.opacity = String(swap);
      layer.style.transform = `translate(${Number(x) * t}%, ${Number(y) * t}%) rotate(${Number(r) * t}deg)`;
      items[index]?.classList.toggle("on", t > 0.5);
      if (index === 0) base.style.transform = `translateY(${28 * t}%)`;
    }
    one("count").textContent = `${loose} von ${layers.length} Baugruppen gelöst`;

    // 3 · Programm: scrolling down moves the panels sideways.
    const p3 = progress(one("seitwaerts"));
    const track = one("track");
    const overhang = Math.max(0, track.scrollWidth - window.innerWidth);
    track.style.transform = `translateX(${-overhang * ease(p3)}px)`;
    one("ghost").style.transform = `translateX(${lerp(10, -60, p3)}%)`;
    for (const [index, numeral] of numerals.entries()) {
      numeral.style.transform = `translateX(${lerp(60, -60, clamp(p3 * 1.2 - index * 0.08, 0, 1))}px)`;
    }

    // 4 · Maßstab: the denominator runs from 45 to 160 and rests at each gauge.
    const p4 = progress(one("massstab"));
    const segment = clamp(p4 * 3, 0, 2.9999);
    const step = Math.floor(segment);
    const denominator =
      p4 >= 1 ? 160 : lerp(SCALES[step] ?? 45, SCALES[step + 1] ?? 160, ease(span(segment - step, 0.25, 0.9)));
    const mm = (HEIGHT_H0_MM * 87) / denominator;
    const benchHeight = one("bench").clientHeight;
    one("ratio").textContent = `1:${Math.round(denominator)}`;
    one("mm").textContent = `${decimal(mm, 1)} mm`;
    one("markLabel").textContent = `${Math.round(mm)} mm`;
    one("benchCrane").style.transform = `scale(${(mm * pxPerMm) / benchHeight})`;
    one("mark").style.transform = `translateY(${benchHeight - mm * pxPerMm}px)`;
    let nearest = 0;
    for (const [index, scale] of SCALES.entries()) {
      if (Math.abs(scale - denominator) < Math.abs((SCALES[nearest] ?? 45) - denominator)) nearest = index;
    }
    for (const [index, chip] of gauge.entries()) chip.classList.toggle("on", index === nearest);

    // 5 · Schluss: two belts of type run against each other.
    const closing = one("schluss").getBoundingClientRect();
    const p5 = clamp((viewport - closing.top) / (viewport + closing.height), 0, 1);
    one("beltA").style.transform = `translateX(${lerp(4, -38, p5)}%)`;
    one("beltB").style.transform = `translateX(${lerp(-42, 0, p5)}%)`;
    for (const element of rising) {
      if (element.getBoundingClientRect().top < viewport * 0.88) element.classList.add("seen");
    }
  }

  let queued = 0;
  const request = () => {
    if (queued) return;
    queued = requestAnimationFrame(() => {
      queued = 0;
      frame();
    });
  };
  const remeasure = () => {
    drawRuler();
    request();
  };

  drawRuler();
  frame();
  window.addEventListener("scroll", request, { passive: true });
  window.addEventListener("resize", remeasure);
  window.addEventListener("load", remeasure);
  return () => {
    window.removeEventListener("scroll", request);
    window.removeEventListener("resize", remeasure);
    window.removeEventListener("load", remeasure);
    if (queued) cancelAnimationFrame(queued);
    root.classList.remove("film-js");
  };
}
