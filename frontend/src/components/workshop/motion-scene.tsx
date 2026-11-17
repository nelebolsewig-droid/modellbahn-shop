"use client";

import { useEffect, useRef, type RefObject } from "react";
import {
  AmbientLight,
  BoxGeometry,
  BufferAttribute,
  BufferGeometry,
  Color,
  DirectionalLight,
  Group,
  HemisphereLight,
  InstancedMesh,
  MathUtils,
  Matrix4,
  Mesh,
  MeshStandardMaterial,
  PerspectiveCamera,
  PMREMGenerator,
  Scene,
  WebGLRenderer,
} from "three";
import { RoomEnvironment } from "three/examples/jsm/environments/RoomEnvironment.js";

import { EDK6_RIG } from "@/lib/workshop/edk6-model";
import { FINISHES, type ExplosionModel } from "@/lib/workshop/explosion";
import { loadMeshFile, type MeshFile } from "@/lib/workshop/mesh-file";
import { RESTING, stepMotion, type MotionMode, type MotionState } from "@/lib/workshop/motion";

type MotionSceneProps = {
  model: ExplosionModel;
  /** The state to show; read on every frame. */
  mode: RefObject<MotionMode>;
  /** Told the speed (m/s of the original) a few times a second, for the read-out. */
  onSpeed: (speed: number) => void;
  /** Stands still in its resting pose (reduced motion). */
  still: boolean;
  onUnavailable: () => void;
};

const SLEEPER_SPACING = 0.65; // metres of the original
const SLEEPER_COUNT = 90;
const RAIL = "#9aa0a6";
const SLEEPER = "#4a3f38";

/**
 * The crane as a painted model in motion: glossy and matte surfaces under a soft studio
 * light, standing, travelling or braking as `mode` says. The camera goes along with the
 * crane; the track runs past underneath.
 */
export default function MotionScene({ model, mode, onSpeed, still, onUnavailable }: MotionSceneProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const stage = stageRef.current;
    const canvas = canvasRef.current;
    if (!stage || !canvas || !model.meshUrl) return;
    let renderer: WebGLRenderer;
    try {
      renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true });
    } catch {
      onUnavailable();
      return;
    }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);

    const scene = new Scene();
    const pmrem = new PMREMGenerator(renderer);
    const room = new RoomEnvironment();
    const environment = pmrem.fromScene(room, 0.04);
    scene.environment = environment.texture;
    scene.add(new AmbientLight(0xffffff, 0.35), new HemisphereLight(0xffffff, 0x1a2a3a, 0.9));
    const key = new DirectionalLight(0xfff1e0, 2.2);
    key.position.set(-80, 140, 120);
    scene.add(key);

    const camera = new PerspectiveCamera(26, 1, 10, 2000);
    const azimuth = MathUtils.degToRad(32);
    const elevation = MathUtils.degToRad(10);
    const target = { x: 8, y: 16, z: 0 };
    const place = (distance: number) => {
      camera.position.set(
        target.x + Math.cos(elevation) * Math.sin(azimuth) * distance,
        target.y + Math.sin(elevation) * distance,
        target.z + Math.cos(elevation) * Math.cos(azimuth) * distance,
      );
      camera.lookAt(target.x, target.y, target.z);
    };

    const disposables: { dispose: () => void }[] = [environment, pmrem, room];
    const crane = new Group();
    scene.add(crane);
    const joints: { slew?: Group; flap?: Group; bogies: Group[]; track?: InstancedMesh; unit: number } = {
      bogies: [],
      unit: 1,
    };

    const build = (file: MeshFile) => {
      const unit = file.unitsPerMetre;
      joints.unit = unit;
      const meshOf = (name: string): Mesh => {
        const part = model.parts.find((entry) =>
          entry.pieces.some((piece) => piece.solids.some((solid) => solid.kind === "mesh" && solid.name === name)),
        );
        const data = file.parts.get(name);
        const geometry = new BufferGeometry();
        if (data) {
          geometry.setAttribute("position", new BufferAttribute(data.positions, 3));
          geometry.setIndex(new BufferAttribute(data.indices, 1));
          geometry.computeVertexNormals();
        }
        const material = new MeshStandardMaterial({
          color: new Color(part?.color ?? "#8d9399"),
          flatShading: true,
          ...FINISHES[part?.finish ?? "matte-metal"],
        });
        disposables.push(geometry, material);
        return new Mesh(geometry, material);
      };
      // A joint: a group at the pivot, its meshes moved back by the pivot.
      const joint = (pivot: string, parent: Group): Group => {
        const [x, y, z] = file.pivots[pivot] ?? [0, 0, 0];
        const group = new Group();
        group.position.set(x - parent.position.x, y - parent.position.y, z - parent.position.z);
        parent.add(group);
        return group;
      };
      const hang = (name: string, group: Group, origin: readonly [number, number, number]) => {
        const mesh = meshOf(name);
        mesh.position.set(-origin[0], -origin[1], -origin[2]);
        group.add(mesh);
      };
      const zero = [0, 0, 0] as const;

      for (const name of EDK6_RIG.fixed) hang(name, crane, zero);
      for (const name of EDK6_RIG.bogies) {
        const group = joint(name, crane);
        hang(name, group, file.pivots[name] ?? zero);
        joints.bogies.push(group);
      }
      const ring = file.pivots.drehkranz ?? zero;
      joints.slew = joint("drehkranz", crane);
      for (const name of EDK6_RIG.superstructure) hang(name, joints.slew, ring);
      joints.flap = joint(EDK6_RIG.flap, joints.slew);
      // The flap's group sits inside the slewing group: its place is relative to the ring.
      const hinge = file.pivots[EDK6_RIG.flap] ?? zero;
      joints.flap.position.set(hinge[0] - ring[0], hinge[1] - ring[1], hinge[2] - ring[2]);
      hang(EDK6_RIG.flap, joints.flap, hinge);

      // The track: two rails and a row of sleepers under the wheels.
      const railTop = (file.pivots["drehgestell-vorn"]?.[1] ?? 0) - 0.39 * unit;
      const half = (EDK6_RIG.gauge / 2) * unit;
      const railGeometry = new BoxGeometry(SLEEPER_COUNT * SLEEPER_SPACING * unit, 0.15 * unit, 0.07 * unit);
      const railMaterial = new MeshStandardMaterial({ color: RAIL, ...FINISHES["matte-metal"] });
      for (const side of [-1, 1]) {
        const rail = new Mesh(railGeometry, railMaterial);
        rail.position.set(0, railTop - 0.075 * unit, side * half);
        scene.add(rail);
      }
      const sleeperGeometry = new BoxGeometry(0.26 * unit, 0.16 * unit, 2.6 * unit);
      const sleeperMaterial = new MeshStandardMaterial({ color: SLEEPER, ...FINISHES.rubber });
      const track = new InstancedMesh(sleeperGeometry, sleeperMaterial, SLEEPER_COUNT);
      const matrix = new Matrix4();
      for (let index = 0; index < SLEEPER_COUNT; index++) {
        matrix.makeTranslation((index - SLEEPER_COUNT / 2) * SLEEPER_SPACING * unit, railTop - 0.23 * unit, 0);
        track.setMatrixAt(index, matrix);
      }
      scene.add(track);
      joints.track = track;
      disposables.push(railGeometry, railMaterial, sleeperGeometry, sleeperMaterial);
    };

    const abort = new AbortController();
    loadMeshFile(model.meshUrl, abort.signal).then(
      (file) => {
        if (!abort.signal.aborted) build(file);
      },
      () => {
        if (!abort.signal.aborted) onUnavailable();
      },
    );

    const resize = () => {
      const rect = stage.getBoundingClientRect();
      const width = Math.max(1, rect.width);
      const height = Math.max(1, rect.height);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      // Upright stages step back so the boom stays in the picture.
      place(camera.aspect < 1 ? 380 : 300);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(stage);
    resize();

    let state: MotionState = RESTING;
    let shown: MotionMode | null = null;
    let last = performance.now();
    let told = 0;
    let frame = 0;
    const draw = (now: number) => {
      const seconds = Math.min(0.05, (now - last) / 1000);
      last = now;
      if (!still) {
        const current = mode.current;
        state = stepMotion(state, current, seconds, current !== shown);
        shown = current;
      }
      crane.rotation.z = -state.pitch;
      if (joints.slew) joints.slew.rotation.y = state.slew;
      if (joints.flap) joints.flap.rotation.z = state.flap;
      joints.bogies.forEach((bogie, index) => {
        bogie.rotation.y = index === 0 ? state.bogieYaw : -state.bogieYaw;
      });
      // The crane travels towards +x, so the sleepers run past towards -x and wrap around.
      if (joints.track) joints.track.position.x = -((state.travel % SLEEPER_SPACING) * joints.unit);
      renderer.render(scene, camera);
      if (now - told > 150) {
        told = now;
        onSpeed(state.speed);
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(frame);
      abort.abort();
      observer.disconnect();
      for (const item of disposables) item.dispose();
      renderer.dispose();
    };
  }, [model, mode, onSpeed, still, onUnavailable]);

  return (
    <div ref={stageRef} className="absolute inset-0">
      <canvas
        ref={canvasRef}
        aria-label={`3D-Ansicht: ${model.name} in Bewegung`}
        className="absolute inset-0 block size-full"
      />
    </div>
  );
}
