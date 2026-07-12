"use client";

import { motion } from "framer-motion";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuthStore } from "@/features/authentication/store/authStore";

const ROUTE_STOPS = [
  { cx: 60, cy: 340 },
  { cx: 160, cy: 180 },
  { cx: 260, cy: 260 },
  { cx: 340, cy: 90 },
];

const PATH_D = "M60 340 C 110 250, 130 220, 160 180 S 230 300, 260 260 S 300 130, 340 90";

export default function SplashPage() {
  const router = useRouter();
  const isHydrated = useAuthStore((s) => s.isHydrated);
  const user = useAuthStore((s) => s.user);
  const [minDelayElapsed, setMinDelayElapsed] = useState(false);

  useEffect(() => {
    // Keep the splash on screen a beat even if hydration is instant, so the
    // animation always gets to play rather than flashing.
    const timer = setTimeout(() => setMinDelayElapsed(true), 1800);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (isHydrated && minDelayElapsed) {
      router.replace(user ? "/home" : "/login");
    }
  }, [isHydrated, minDelayElapsed, user, router]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-brand-900">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.6, ease: "easeOut" }}
        className="relative"
      >
        <svg width="360" height="400" viewBox="0 0 400 400" fill="none" aria-hidden="true">
          <motion.path
            d={PATH_D}
            stroke="#7fe6b3"
            strokeWidth="3"
            strokeLinecap="round"
            fill="none"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ duration: 1.4, ease: "easeInOut", delay: 0.2 }}
          />
          {ROUTE_STOPS.map((stop, i) => (
            <motion.circle
              key={`${stop.cx}-${stop.cy}`}
              cx={stop.cx}
              cy={stop.cy}
              r={i === ROUTE_STOPS.length - 1 ? 10 : 6}
              fill={i === ROUTE_STOPS.length - 1 ? "#ff7a3d" : "#7fe6b3"}
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              transition={{ duration: 0.35, delay: 0.3 + i * 0.35 }}
            />
          ))}
        </svg>
      </motion.div>

      <motion.div
        className="flex flex-col items-center gap-2 text-center"
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, delay: 1.1 }}
      >
        <h1 className="font-display text-3xl font-semibold tracking-tight text-white">SmartTrip AI</h1>
        <p className="text-sm text-brand-100">Every trip has a shape.</p>
      </motion.div>

      <motion.div
        className="h-1 w-40 overflow-hidden rounded-full bg-white/10"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.3 }}
      >
        <motion.div
          className="h-full rounded-full bg-brand-300"
          initial={{ width: "0%" }}
          animate={{ width: "100%" }}
          transition={{ duration: 1.6, delay: 1.3, ease: "easeInOut" }}
        />
      </motion.div>
    </div>
  );
}
