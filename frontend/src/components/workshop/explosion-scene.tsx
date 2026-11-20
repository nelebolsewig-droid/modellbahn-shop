"use client";

import { useEffect, useRef, type RefObject } from "react";
import {
  AmbientLight,
  Box3,
  BoxGeometry,
  BufferAttribute,
  BufferGeometry,
  Color,
  CylinderGeometry,
  DirectionalLight,
  EdgesGeometry,
  Group,
  LineBasicMaterial,
  LineSegments,
  MathUtils,
  Mesh,
  MeshLambertMaterial,
  OrthographicCamera,
  Scene,
  Vector3,
  WebGLRenderer,
} from "three";

import { balloonOpacity, partShare, type ExplosionModel, type Solid } from "@/lib/workshop/explosion";

type ExplosionSceneProps = {
  model: ExplosionModel;
  /** How far the model is taken apart, 0 to 1; read on every frame. */
  explosion: RefObject<number>;
  highlighted: number | null;
  onHighlight: (position: number | null) => void;
  spinning: boolean;
  /** Called once if the browser cannot draw WebGL. */
  onUnavailable: () => void;
};

type MovingPiece = { group: Group; center: Vector3; direction: Vector3; distance: number };
type ScenePart = { position: number; order: number; material: MeshLambertMaterial; pieces: MovingPiece[] };

// Wide enough for the fully exploded model while it turns (mm); upright phones get closer.
const HALF_WIDTH = 100;
const HALF_WIDTH_UPRIGHT = 80;
const HALF_HEIGHT = 68;
const UPRIGHT_ASPECT = 0.75;
const EDGE_ANGLE = 28;
const TURN_PER_SECOND = 0.18;
const DRAG_PER_PIXEL = 0.012;
const BALLOON_OFFSET = 44;
const BALLOON_RADIUS = 13;

function token(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/** Reads a display mesh written by scripts/werkstatt/build_edk6_mesh.py, flat-shaded. */
async function loadMesh(url: string, signal: AbortSignal): Promise<BufferGeometry> {
  const response = await fetch(url, { signal });
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  const buffer = await response.arrayBuffer();
  const head = new DataView(buffer);
  const vertices = head.getUint32(4, true);
  const indices = head.getUint32(8, true);
  const quantum = head.getFloat32(12, true);
  const raw = new Int16Array(buffer, 16, vertices * 3);
  const start = 16 + vertices * 6;
  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new BufferAttribute(Float32Array.from(raw, (value) => value * quantum), 3));
  geometry.setIndex(new BufferAttribute(new Uint32Array(buffer.slice(start, start + indices * 4)), 1));
  const flat = geometry.toNonIndexed();
  geometry.dispose();
  flat.computeVertexNormals();
  return flat;
}

function geometryOf(solid: Exclude<Solid, { kind: "mesh" }>): BufferGeometry {
  if (solid.kind === "box") {
    const geometry = new BoxGeometry(...solid.size);
    geometry.translate(...solid.at);
    return geometry;
  }
  const geometry = new CylinderGeometry(solid.radius, solid.radius, solid.length, solid.segments ?? 28);
  if (solid.axis === "z") geometry.rotateX(Math.PI / 2);
  if (solid.axis === "x") geometry.rotateZ(Math.PI / 2);
  geometry.translate(...solid.at);
  return geometry;
}

/**
 * The model drawn like a construction plan: light faces with Prussian-blue edges, an
 * orthographic view that turns slowly, parts that move apart with the explosion, and a
 * numbered balloon on each position.
 */
export default function ExplosionScene({
  model,
  explosion,
  highlighted,
  onHighlight,
  spinning,
  onUnavailable,
}: ExplosionSceneProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const balloonRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const leaderRefs = useRef<(SVGLineElement | null)[]>([]);
  const anchorRefs = useRef<(SVGCircleElement | null)[]>([]);
  const partsRef = useRef<ScenePart[]>([]);
  const spinningRef = useRef(spinning);
  const colors = useRef({ fill: "#fafaf8", highlight: "#d9e4ee" });

  useEffect(() => {
    spinningRef.current = spinning;
  }, [spinning]);

  useEffect(() => {
    for (const part of partsRef.current) {
      part.material.color.set(part.position === highlighted ? colors.current.highlight : colors.current.fill);
    }
  }, [highlighted]);

  useEffect(() => {
    const stage = stageRef.current;
    const canvas = canvasRef.current;
    if (!stage || !canvas) return;
    let renderer: WebGLRenderer;
    try {
      renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true });
    } catch {
      onUnavailable();
      return;
    }
    colors.current = { fill: token("--stage", "#fafaf8"), highlight: token("--drawing-grid", "#d9e4ee") };
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);

    const scene = new Scene();
    scene.add(new AmbientLight(0xffffff, 2.4));
    const sun = new DirectionalLight(0xffffff, 1);
    sun.position.set(-0.6, 1, 0.8);
    scene.add(sun);

    const camera = new OrthographicCamera(-1, 1, 1, -1, 1, 2000);
    const elevation = MathUtils.degToRad(24);
    const azimuth = MathUtils.degToRad(38);
    camera.position.set(
      Math.cos(elevation) * Math.sin(azimuth) * 600,
      Math.sin(elevation) * 600 + 6,
      Math.cos(elevation) * Math.cos(azimuth) * 600,
    );
    camera.lookAt(0, 6, 0);

    const view = model.frame ?? { halfWidth: HALF_WIDTH, halfHeight: HALF_HEIGHT, lift: 16 };
    const loading = new AbortController();
    const root = new Group();
    root.position.y = -view.lift;
    scene.add(root);
    const lineMaterial = new LineBasicMaterial({ color: new Color(token("--drawing-line", "#003153")) });
    const disposables: { dispose: () => void }[] = [lineMaterial];

    partsRef.current = model.parts.map((part) => {
      const material = new MeshLambertMaterial({
        color: new Color(colors.current.fill),
        polygonOffset: true,
        polygonOffsetFactor: 1,
        polygonOffsetUnits: 1,
      });
      disposables.push(material);
      const pieces = part.pieces.map((piece) => {
        const group = new Group();
        const moving: MovingPiece = {
          group,
          center: new Vector3(),
          direction: new Vector3(...piece.direction).normalize(),
          distance: piece.distance,
        };
        const add = (geometry: BufferGeometry) => {
          const edges = new EdgesGeometry(geometry, EDGE_ANGLE);
          disposables.push(geometry, edges);
          group.add(new Mesh(geometry, material), new LineSegments(edges, lineMaterial));
          // The centre without the explosion offset, as the balloons add it themselves.
          const offset = group.position.clone();
          group.position.set(0, 0, 0);
          new Box3().setFromObject(group).getCenter(moving.center);
          group.position.copy(offset);
        };
        for (const solid of piece.solids) {
          if (solid.kind !== "mesh") add(geometryOf(solid));
          else
            loadMesh(solid.url, loading.signal).then(
              (geometry) => (loading.signal.aborted ? geometry.dispose() : add(geometry)),
              () => {},
            );
        }
        root.add(group);
        return moving;
      });
      return { position: part.position, order: part.order, material, pieces };
    });
    const lastOrder = Math.max(...model.parts.map((part) => part.order));

    let width = 1;
    let height = 1;
    const resize = () => {
      const rect = stage.getBoundingClientRect();
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
      renderer.setSize(width, height, false);
      const aspect = width / height;
      const halfWidth = view.halfWidth * (aspect < UPRIGHT_ASPECT ? HALF_WIDTH_UPRIGHT / HALF_WIDTH : 1);
      const halfHeight = Math.max(view.halfHeight, halfWidth / aspect);
      camera.left = -halfHeight * aspect;
      camera.right = halfHeight * aspect;
      camera.top = halfHeight;
      camera.bottom = -halfHeight;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(stage);
    resize();

    // Turning: slowly by itself, or by dragging sideways (vertical drags scroll the page).
    let angle = -0.55;
    let drag: { x: number; angle: number } | null = null;
    const down = (event: PointerEvent) => {
      drag = { x: event.clientX, angle };
      canvas.setPointerCapture(event.pointerId);
    };
    const move = (event: PointerEvent) => {
      if (drag) angle = drag.angle + (event.clientX - drag.x) * DRAG_PER_PIXEL;
    };
    const up = () => {
      drag = null;
    };
    canvas.addEventListener("pointerdown", down);
    canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up);
    canvas.addEventListener("pointercancel", up);

    const point = new Vector3();
    let last = performance.now();
    let frame = 0;
    const draw = (now: number) => {
      const seconds = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (spinningRef.current && !drag) angle += seconds * TURN_PER_SECOND;
      root.rotation.y = angle;
      const amount = explosion.current;
      for (const part of partsRef.current) {
        const share = partShare(amount, part.order, lastOrder);
        for (const piece of part.pieces)
          piece.group.position.copy(piece.direction).multiplyScalar(piece.distance * share);
      }
      root.updateMatrixWorld(true);
      renderer.render(scene, camera);

      // Balloons follow each position's first piece, pushed away from the middle.
      const opacity = balloonOpacity(amount);
      partsRef.current.forEach((part, index) => {
        const balloon = balloonRefs.current[index];
        const leader = leaderRefs.current[index];
        const anchor = anchorRefs.current[index];
        const piece = part.pieces[0];
        if (!balloon || !leader || !anchor || !piece) return;
        point.copy(piece.center).add(piece.group.position);
        root.localToWorld(point);
        point.project(camera);
        const ax = ((point.x + 1) / 2) * width;
        const ay = ((1 - point.y) / 2) * height;
        const length = Math.hypot(ax - width / 2, ay - height / 2) || 1;
        const bx = Math.min(width - 22, Math.max(22, ax + ((ax - width / 2) / length) * BALLOON_OFFSET));
        const by = Math.min(height - 22, Math.max(56, ay + ((ay - height / 2) / length) * BALLOON_OFFSET));
        const reach = Math.hypot(bx - ax, by - ay) || 1;
        balloon.style.transform = `translate(${bx}px, ${by}px)`;
        balloon.style.opacity = String(opacity);
        balloon.style.visibility = opacity > 0.02 ? "visible" : "hidden";
        balloon.tabIndex = opacity > 0.5 ? 0 : -1;
        leader.setAttribute("x1", String(ax));
        leader.setAttribute("y1", String(ay));
        leader.setAttribute("x2", String(bx - ((bx - ax) / reach) * BALLOON_RADIUS));
        leader.setAttribute("y2", String(by - ((by - ay) / reach) * BALLOON_RADIUS));
        leader.style.opacity = String(opacity);
        anchor.setAttribute("cx", String(ax));
        anchor.setAttribute("cy", String(ay));
        anchor.style.opacity = String(opacity);
      });
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);

    return () => {
      loading.abort();
      cancelAnimationFrame(frame);
      observer.disconnect();
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointercancel", up);
      for (const item of disposables) item.dispose();
      renderer.dispose();
      partsRef.current = [];
    };
  }, [model, explosion, onUnavailable]);

  return (
    <div ref={stageRef} className="absolute inset-0">
      <canvas
        ref={canvasRef}
        aria-label={`3D-Ansicht: ${model.name} in ${model.parts.length} Positionen. Seitlich ziehen dreht das Modell.`}
        className="absolute inset-0 block size-full cursor-grab touch-pan-y active:cursor-grabbing"
      />
      <svg aria-hidden="true" className="pointer-events-none absolute inset-0 size-full overflow-visible">
        {model.parts.map((part, index) => (
          <g key={part.position} className="fill-drawing-line stroke-drawing-line">
            <line
              ref={(element) => {
                leaderRefs.current[index] = element;
              }}
              strokeWidth={1}
              style={{ opacity: 0 }}
            />
            <circle
              ref={(element) => {
                anchorRefs.current[index] = element;
              }}
              r={1.8}
              strokeWidth={0}
              style={{ opacity: 0 }}
            />
          </g>
        ))}
      </svg>
      {model.parts.map((part, index) => (
        <button
          key={part.position}
          ref={(element) => {
            balloonRefs.current[index] = element;
          }}
          type="button"
          tabIndex={-1}
          aria-label={`Position ${part.position}: ${part.name}`}
          onMouseEnter={() => onHighlight(part.position)}
          onMouseLeave={() => onHighlight(null)}
          onFocus={() => onHighlight(part.position)}
          onBlur={() => onHighlight(null)}
          style={{ visibility: "hidden", opacity: 0 }}
          className={
            "absolute top-0 left-0 -mt-[13px] -ml-[13px] size-[26px] rounded-full border border-accent font-mono text-[12px] leading-[24px] " +
            "transition-colors duration-150 ease-out focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-accent " +
            (highlighted === part.position ? "bg-accent text-on-accent" : "bg-stage text-accent")
          }
        >
          {part.position}
        </button>
      ))}
    </div>
  );
}
