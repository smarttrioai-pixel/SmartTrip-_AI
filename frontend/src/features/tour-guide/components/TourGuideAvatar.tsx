"use client";

import Image from "next/image";
import { Pause, Play, Volume2, VolumeX, Camera } from "lucide-react";

import { Button } from "@/shared/components/ui/button";

interface TourGuideAvatarProps {
  destination?: string;
  subtitle: string;
  isSpeaking: boolean;
  isPaused: boolean;
  onTogglePause: () => void;
  onStopSpeech: () => void;
  onOpenCamera: () => void;
}

export function TourGuideAvatar({
  destination,
  subtitle,
  isSpeaking,
  isPaused,
  onTogglePause,
  onStopSpeech,
  onOpenCamera,
}: TourGuideAvatarProps) {
  return (
    <div className="relative flex flex-col overflow-hidden rounded-2xl border border-ink-200 bg-ink-900 shadow-lg dark:border-ink-700 min-h-[420px]">
      {/* Background */}
      <div
        className="absolute inset-0 bg-cover bg-center opacity-40"
        style={{
          backgroundImage: destination
            ? `linear-gradient(to bottom, rgba(0,0,0,0.2), rgba(0,0,0,0.7)), url('https://images.unsplash.com/photo-1582515073490-39981379c062?w=800&q=80')`
            : undefined,
        }}
      />

      {/* Avatar */}
      <div className="relative flex flex-1 items-end justify-center pt-8 pb-24">
        <div className="relative h-72 w-56 sm:h-80 sm:w-64">
          <Image
            src="/avatar/tour-guide.svg"
            alt="AI Tour Guide"
            fill
            className="object-contain drop-shadow-2xl"
            priority
          />
        </div>
      </div>

      {/* Top controls */}
      <div className="absolute top-4 right-4 flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={onOpenCamera}
          className="border-white/20 bg-ink-950/60 text-white hover:bg-ink-950/80 backdrop-blur-sm"
        >
          <Camera className="h-3.5 w-3.5" />
          Identify
        </Button>
      </div>

      {/* Subtitle bar */}
      <div className="absolute bottom-0 left-0 right-0 bg-ink-950/85 backdrop-blur-md border-t border-ink-700/50 p-4">
        <p className="text-sm text-white/90 leading-relaxed min-h-[2.5rem] line-clamp-3">
          {subtitle || "Your guide is ready. Tap 'Yes, let's start' to begin Day 1."}
        </p>

        <div className="mt-3 flex items-center gap-3">
          <button
            type="button"
            onClick={onTogglePause}
            disabled={!isSpeaking && !isPaused}
            className="rounded-lg p-2 text-white/80 hover:bg-white/10 disabled:opacity-40"
            aria-label={isPaused ? "Resume speech" : "Pause speech"}
          >
            {isPaused ? <Play className="h-4 w-4" /> : <Pause className="h-4 w-4" />}
          </button>

          <button
            type="button"
            onClick={onStopSpeech}
            disabled={!isSpeaking && !isPaused}
            className="rounded-lg p-2 text-white/80 hover:bg-white/10 disabled:opacity-40"
            aria-label="Stop speech"
          >
            <VolumeX className="h-4 w-4" />
          </button>

          <div className="flex-1 flex items-center gap-1 px-2">
            {isSpeaking &&
              !isPaused &&
              Array.from({ length: 12 }).map((_, i) => (
                <span
                  key={i}
                  className="w-1 rounded-full bg-brand-400 animate-pulse"
                  style={{
                    height: `${8 + (i % 4) * 4}px`,
                    animationDelay: `${i * 0.08}s`,
                  }}
                />
              ))}
          </div>

          <Volume2
            className={`h-4 w-4 shrink-0 ${isSpeaking ? "text-brand-400" : "text-white/40"}`}
            aria-hidden="true"
          />
        </div>
      </div>
    </div>
  );
}
