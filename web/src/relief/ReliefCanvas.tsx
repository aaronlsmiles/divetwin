import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import { BufferAttribute, BufferGeometry, type Group } from "three";
import type { ReliefFrame } from "./frameData";

export const ORBIT_LIMIT_DEG = 25;                      // docs/DESIGN.md: an orbit limited to about +-25 degrees
const rad = (d: number) => (d * Math.PI) / 180;
export const clampOrbit = (deg: number): number => Math.max(-ORBIT_LIMIT_DEG, Math.min(ORBIT_LIMIT_DEG, deg));

function geometry(positions: Float32Array, indices: Uint32Array, colours?: Float32Array): BufferGeometry {
  const g = new BufferGeometry();
  g.setAttribute("position", new BufferAttribute(positions, 3));
  if (colours) g.setAttribute("color", new BufferAttribute(colours, 3));
  g.setIndex(new BufferAttribute(indices, 1));
  return g;
}

function Scene({ frame, instant }: { frame: ReliefFrame; instant: boolean }) {
  const group = useRef<Group>(null);
  const target = useRef({ yaw: 0, pitch: 0 });
  const { gl, invalidate } = useThree();
  const real = useMemo(() => geometry(frame.real.positions, frame.real.indices), [frame.real]);
  const dream = useMemo(() => (frame.dream ? geometry(frame.dream.positions, frame.dream.indices, frame.dream.colours) : null), [frame.dream]);
  useEffect(() => () => { real.dispose(); dream?.dispose(); }, [real, dream]);
  useEffect(() => {
    const el = gl.domElement;
    let down: { x: number; y: number; yaw: number; pitch: number } | null = null;
    const onDown = (e: PointerEvent) => { down = { x: e.clientX, y: e.clientY, ...target.current }; el.setPointerCapture(e.pointerId); };
    const onMove = (e: PointerEvent) => {
      if (!down) return;
      target.current = { yaw: clampOrbit(down.yaw + (e.clientX - down.x) * 0.15), pitch: clampOrbit(down.pitch + (e.clientY - down.y) * 0.15) };
      invalidate();
    };
    const onUp = () => { down = null; };
    el.addEventListener("pointerdown", onDown); el.addEventListener("pointermove", onMove);
    el.addEventListener("pointerup", onUp); el.addEventListener("pointercancel", onUp);
    return () => { el.removeEventListener("pointerdown", onDown); el.removeEventListener("pointermove", onMove); el.removeEventListener("pointerup", onUp); el.removeEventListener("pointercancel", onUp); };
  }, [gl, invalidate]);
  useFrame((_, dt) => {
    const g = group.current;
    if (!g) return;
    const k = instant ? 1 : 1 - Math.exp(-dt / 0.08);           // the orbit eases (about 240 ms to settle); reduced motion: instant
    g.rotation.y += (rad(target.current.yaw) - g.rotation.y) * k;
    g.rotation.x += (rad(target.current.pitch) - g.rotation.x) * k;
    if (Math.abs(rad(target.current.yaw) - g.rotation.y) > 1e-4 || Math.abs(rad(target.current.pitch) - g.rotation.x) > 1e-4) invalidate();
  });
  return (
    <group ref={group} position={[0, 0, -4]}>
      <group position={[0, 0, 4]}>
        <mesh geometry={real}><meshBasicMaterial color="#b3aa9e" wireframe transparent opacity={0.5} /></mesh>
        {dream && <mesh geometry={dream}><meshBasicMaterial vertexColors side={2} /></mesh>}
      </group>
    </group>
  );
}

/** The relief in WebGL: two surfaces, orbit by drag, limited to about +-25 degrees, demand-driven (it draws when something changes). */
export default function ReliefCanvas({ frame, instant, label }: { frame: ReliefFrame; instant: boolean; label: string }) {
  return (
    <Canvas className="relief-canvas" role="img" aria-label={label} frameloop="demand" dpr={[1, 2]} camera={{ position: [0, 1.2, 2.7], fov: 45, near: 0.1, far: 100 }}
      onCreated={({ camera }) => camera.lookAt(0, 0.25, -4)} gl={{ antialias: true }}>
      <Scene frame={frame} instant={instant} />
    </Canvas>
  );
}
