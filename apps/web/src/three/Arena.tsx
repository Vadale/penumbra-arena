import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useMemo } from "react";
import { usePenumbraStore } from "../streams/store";

/**
 * Phase 1 visualisation: agents on a 2D circular layout, rendered as
 * coloured dots in a 3D canvas. Goals are highlighted gold. Edges and
 * fuzzy clouds come in later phases — by then the backend will ship a
 * topology snapshot and the Bayesian posterior σ.
 */

const RING_RADIUS = 5;

function layoutNode(nodeId: number, totalNodes: number): [number, number, number] {
  const angle = (nodeId / Math.max(totalNodes, 1)) * Math.PI * 2;
  return [Math.cos(angle) * RING_RADIUS, Math.sin(angle) * RING_RADIUS, 0];
}

function Agent({ id, position, total }: { id: number; position: number; total: number }) {
  const xyz = useMemo(() => layoutNode(position, total), [position, total]);
  const hue = (id * 0.61803398) % 1; // golden-ratio palette
  const color = `hsl(${Math.floor(hue * 360)} 70% 60%)`;
  return (
    <mesh position={xyz}>
      <sphereGeometry args={[0.12, 16, 16]} />
      <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.4} />
    </mesh>
  );
}

function Goal({ position, total }: { position: number; total: number }) {
  const xyz = useMemo(() => layoutNode(position, total), [position, total]);
  return (
    <mesh position={xyz}>
      <torusGeometry args={[0.3, 0.05, 16, 32]} />
      <meshStandardMaterial color="#facc15" emissive="#facc15" emissiveIntensity={0.6} />
    </mesh>
  );
}

export function Arena() {
  const lastFrame = usePenumbraStore((s) => s.lastFrame);
  const connected = usePenumbraStore((s) => s.connected);

  if (!connected || lastFrame === null) {
    return (
      <div className="grid h-full place-items-center text-slate-400">
        <div className="text-center">
          <div className="text-sm uppercase tracking-wider">Awaiting simulation</div>
          <div className="mt-1 text-xs opacity-60">
            run <code className="rounded bg-slate-800 px-1">just api-dev</code>
          </div>
        </div>
      </div>
    );
  }

  const total = Math.max(
    ...Object.values(lastFrame.agent_positions).map((p) => p + 1),
    ...lastFrame.arena_goals.map((g) => g + 1),
    20,
  );

  return (
    <Canvas camera={{ position: [0, 0, 12], fov: 50 }}>
      <ambientLight intensity={0.4} />
      <pointLight position={[10, 10, 10]} intensity={1.2} />
      <OrbitControls enablePan={false} enableZoom={false} />
      {Object.entries(lastFrame.agent_positions).map(([idStr, position]) => (
        <Agent key={idStr} id={Number(idStr)} position={position} total={total} />
      ))}
      {lastFrame.arena_goals.map((goal) => (
        <Goal key={`goal-${goal}`} position={goal} total={total} />
      ))}
    </Canvas>
  );
}
