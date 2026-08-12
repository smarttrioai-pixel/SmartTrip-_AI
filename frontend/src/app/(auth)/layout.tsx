import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      {/* Brand panel — the "signature element": a route-line motif standing
          in for a trip itinerary, unique to a travel product. */}
      <aside className="relative hidden overflow-hidden bg-brand-900 lg:flex lg:flex-col lg:justify-between lg:p-12">
        <div className="pointer-events-none absolute inset-0 opacity-40">
          <RouteLineDecoration />
        </div>
        <span className="relative font-display text-xl font-semibold tracking-tight text-white">
          SmartTrip AI
        </span>
        <blockquote className="relative max-w-sm font-display text-3xl font-medium leading-tight text-white">
          Every trip has a shape. We help you find yours.
        </blockquote>
      </aside>

      <main className="flex items-center justify-center px-6 py-16">
        <div className="w-full max-w-sm">{children}</div>
      </main>
    </div>
  );
}

function RouteLineDecoration() {
  return (
    <svg viewBox="0 0 400 800" className="h-full w-full" preserveAspectRatio="xMidYMid slice">
      <path
        d="M40 60 C 180 120, 60 260, 220 320 S 340 480, 160 560 S 60 700, 300 760"
        fill="none"
        stroke="#7fe6b3"
        strokeWidth="2"
        strokeDasharray="6 10"
      />
      {[
        [40, 60],
        [220, 320],
        [160, 560],
        [300, 760],
      ].map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="5" fill="#ff7a3d" />
      ))}
    </svg>
  );
}
