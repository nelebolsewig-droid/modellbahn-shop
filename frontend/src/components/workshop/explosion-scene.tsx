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

import { balloonOpacity, paintAt, partShare, type ExplosionModel, type Solid } from "@/lib/workshop/explosion";
import { loadMeshFile, type PartMesh } from "@/lib/workshop/mesh-file";

type ExplosionSceneProps = {
  model: ExplosionModel;
  /** How far the model is taken apart, 0 to 1; read on every frame. */
  explosion: RefObject<number>;
  highlighted: number | null;
  onHighlight: (position: number | null) => void;
  spinning: boolean;
  /** Without the numbered balloons: the model as a picture, e.g. on the start page. */
  plain?: boolean;
  /** Brings the model closer (1 = the exploded model fits while it turns). */
  zoom?: number;
  /** Colours of the plain drawing where the stage is not the light sheet (hex). */
  palette?: { fill: string; line: string };
  /** Called once if the browser cannot draw WebGL. */
  onUnavailable: () => void;
};

type MovingPiece = { group: Group; center: Vector3; direction: Vector3; distance: number };
type ScenePart = {
  position: number;
  order: number;
  material: MeshLambertMaterial;
  /** The part's paint; null for a part that stays the colour of the drawing. */
  paint: Color | null;
  pieces: MovingPiece[];
};

// Wide enough for the fully exploded model while it turns (mm); upright phones get closer.
const HALF_WIDTH = 100;
const HALF_WIDTH_UPRIGHT = 80;
const HALF_HEIGHT = 68;
const UPRIGHT_ASPECT = 0.75;
const EDGE_ANGLE = 28;
// Printed shapes are rounder than the placeholder's boxes: only their sharper edges are drawn.
const MESH_EDGE_ANGLE = 38;
const TURN_PER_SECOND = 0.18;
const DRAG_PER_PIXEL = 0.012;
const BALLOON_OFFSET = 44;
const BALLOON_RADIUS = 13;

function token(name: string, fallback: string): string {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function geometryOf(solid: Solid, meshes: ReadonlyMap<string, PartMesh>): BufferGeometry {
  if (solid.kind === "mesh") {
    const mesh = meshes.get(solid.name);
    const geometry = new BufferGeometry();
    if (mesh) {
      geometry.setAttribute("position", new BufferAttribute(mesh.positions, 3));
      geometry.setIndex(new BufferAttribute(mesh.indices, 1));
      geometry.computeVertexNormals();
    }
    return geometry;
  }
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
 * numbered balloon on each position. A real model (one with a mesh file) stands in its
 * paint while it is whole; the colour drains into the drawing as it comes apart.
 */
export default function ExplosionScene({
  model,
  explosion,
  highlighted,
  onHighlight,
  spinning,
  palette,
  zoom = 1,
  plain = false,
  onUnavailable,
}: ExplosionSceneProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const balloonRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const leaderRefs = useRef<(SVGLineElement | null)[]>([]);
  const anchorRefs = useRef<(SVGCircleElement | null)[]>([]);
  const partsRef = useRef<ScenePart[]>([]);
  const spinningRef = useRef(spinning);
  const highlightedRef = useRef(highlighted);

  useEffect(() => {
    spinningRef.current = spinning;
  }, [spinning]);

  useEffect(() => {
    highlightedRef.current = highlighted;
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
    const fill = new Color(palette?.fill ?? token("--stage", "#fafaf8"));
    const lit = new Color(token("--drawing-grid", "#d9e4ee"));
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

    const root = new Group();
    root.position.y = -16;
    scene.add(root);
    const lineMaterial = new LineBasicMaterial({ color: new Color(palette?.line ?? token("--drawing-line", "#003153")) });
    const disposables: { dispose: () => void }[] = [lineMaterial];

    const build = (meshes: ReadonlyMap<string, PartMesh>) => model.parts.map((part) => {
      const material = new MeshLambertMaterial({
        color: fill.clone(),
        polygonOffset: true,
        polygonOffsetFactor: 1,
        polygonOffsetUnits: 1,
      });
      disposables.push(material);
      const pieces = part.pieces.map((piece) => {
        const group = new Group();
        for (const solid of piece.solids) {
          const geometry = geometryOf(solid, meshes);
          const edges = new EdgesGeometry(geometry, solid.kind === "mesh" ? MESH_EDGE_ANGLE : EDGE_ANGLE);
          disposables.push(geometry, edges);
          group.add(new Mesh(geometry, material), new LineSegments(edges, lineMaterial));
        }
        root.add(group);
        return {
          group,
          center: new Box3().setFromObject(group).getCenter(new Vector3()),
          direction: new Vector3(...piece.direction).normalize(),
          distance: piece.distance,
        };
      });
      return {
        position: part.position,
        order: part.order,
        material,
        paint: part.color ? new Color(part.color) : null,
        pieces,
      };
    });
    // The placeholder is built at once; a real model appears when its mesh file has arrived.
    const abort = new AbortController();
    if (model.meshUrl) {
      loadMeshFile(model.meshUrl, abort.signal).then(
        (file) => {
          if (!abort.signal.aborted) partsRef.current = build(file.parts);
        },
        () => {
          if (!abort.signal.aborted) onUnavailable();
        },
      );
    } else {
      partsRef.current = build(new Map());
    }
    const lastOrder = Math.max(...model.parts.map((part) => part.order));

    let width = 1;
    let height = 1;
    const resize = () => {
      const rect = stage.getBoundingClientRect();
      width = Math.max(1, rect.width);
      height = Math.max(1, rect.height);
      renderer.setSize(width, height, false);
      const aspect = width / height;
      const halfWidth = aspect < UPRIGHT_ASPECT ? HALF_WIDTH_UPRIGHT : HALF_WIDTH;
      const halfHeight = Math.max(HALF_HEIGHT, halfWidth / aspect);
      camera.left = -halfHeight * aspect;
      camera.right = halfHeight * aspect;
      camera.top = halfHeight;
      camera.bottom = -halfHeight;
      camera.zoom = zoom;
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
      const paint = paintAt(amount);
      for (const part of partsRef.current) {
        const share = partShare(amount, part.order, lastOrder);
        if (part.position === highlightedRef.current) part.material.color.copy(lit);
        else if (part.paint) part.material.color.copy(fill).lerp(part.paint, paint);
        else part.material.color.copy(fill);
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
      cancelAnimationFrame(frame);
      abort.abort();
      observer.disconnect();
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointermove", move);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointercancel", up);
      for (const item of disposables) item.dispose();
      renderer.dispose();
      partsRef.current = [];
    };
  }, [model, explosion, palette, zoom, onUnavailable]);

  return (
    <div ref={stageRef} className="absolute inset-0">
      <canvas
        ref={canvasRef}
        aria-label={`3D-Ansicht: ${model.name} in ${model.parts.length} Positionen. Seitlich ziehen dreht das Modell.`}
        className="absolute inset-0 block size-full cursor-grab touch-pan-y active:cursor-grabbing"
      />
      <svg aria-hidden="true" className="pointer-events-none absolute inset-0 size-full overflow-visible">
        {(plain ? [] : model.parts).map((part, index) => (
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
      {(plain ? [] : model.parts).map((part, index) => (
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
