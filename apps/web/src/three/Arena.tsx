import { OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useMemo } from "react";
import { usePenumbraStore } from "../streams/store";

/**
 * Penumbra arena viewer.
 *
 * Each agent is rendered as a crisp coloured dot wrapped in a fuzzy
 * halo whose alpha + radius scale with the *variance of the agent's
 * recent position* — a poor man's posterior σ that lives entirely on
 * the client. Agents that stay still get a tight halo (we're sure
 * where they are); agents that wander get a wide halo (we know they're
 * somewhere in a region but not precisely where). This is the literal
 * Penumbra: the visible part is the agent, the shadow is its
 * uncertainty.
 *
 * Goals show as gold tori on the same ring layout.
 */

const RING_RADIUS = 5;
const HALO_BASE_RADIUS = 0.22;
const HALO_VARIANCE_GAIN = 1.6;

function layoutNode(nodeId: number, totalNodes: number): [number, number, number] {
  const angle = (nodeId / Math.max(totalNodes, 1)) * Math.PI * 2;
  return [Math.cos(angle) * RING_RADIUS, Math.sin(angle) * RING_RADIUS, 0];
}

function meanAndStd(values: number[]): { mean: number; std: number } {
  if (values.length === 0) return { mean: 0, std: 0 };
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance = values.reduce((a, b) => a + (b - mean) * (b - mean), 0) / values.length;
  return { mean, std: Math.sqrt(variance) };
}

function Agent({
  id,
  position,
  history,
  total,
}: {
  id: number;
  position: number;
  history: number[];
  total: number;
}) {
  const xyz = useMemo(() => layoutNode(position, total), [position, total]);
  const { std } = useMemo(() => meanAndStd(history), [history]);
  const hue = (id * 0.61803398) % 1;
  const color = `hsl(${Math.floor(hue * 360)} 70% 60%)`;

  const haloRadius = HALO_BASE_RADIUS + std * HALO_VARIANCE_GAIN * 0.08;
  // Higher std → wider AND more transparent halo.
  const haloAlpha = Math.max(0.06, Math.min(0.45, 0.32 - std * 0.04));

  return (
    <group position={xyz}>
      <mesh>
        <sphereGeometry args={[0.12, 16, 16]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.4} />
      </mesh>
      <mesh>
        <sphereGeometry args={[haloRadius, 24, 24]} />
        <meshBasicMaterial color={color} transparent opacity={haloAlpha} depthWrite={false} />
      </mesh>
    </group>
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
  const history = usePenumbraStore((s) => s.agentPositionHistory);

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
      {Object.entries(lastFrame.agent_positions).map(([idStr, position]) => {
        const id = Number(idStr);
        return (
          <Agent
            key={idStr}
            id={id}
            position={position}
            history={history[id] ?? []}
            total={total}
          />
        );
      })}
      {lastFrame.arena_goals.map((goal) => (
        <Goal key={`goal-${goal}`} position={goal} total={total} />
      ))}
    </Canvas>
  );
}
