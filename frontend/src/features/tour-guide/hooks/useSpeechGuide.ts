"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export function useSpeechGuide() {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [subtitle, setSubtitle] = useState("");
  const onEndRef = useRef<(() => void) | null>(null);

  const stop = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
    setIsPaused(false);
    setSubtitle("");
    onEndRef.current = null;
  }, []);

  const speak = useCallback(
    (text: string, onEnd?: () => void) => {
      if (typeof window === "undefined" || !("speechSynthesis" in window)) {
        setSubtitle(text);
        onEnd?.();
        return;
      }

      window.speechSynthesis.cancel();
      onEndRef.current = onEnd ?? null;

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 0.92;
      utterance.pitch = 1;

      utterance.onstart = () => {
        setIsSpeaking(true);
        setIsPaused(false);
        setSubtitle(text);
      };

      utterance.onend = () => {
        setIsSpeaking(false);
        setIsPaused(false);
        const cb = onEndRef.current;
        onEndRef.current = null;
        cb?.();
      };

      utterance.onerror = () => {
        setIsSpeaking(false);
        setIsPaused(false);
        onEndRef.current = null;
      };

      window.speechSynthesis.speak(utterance);
    },
    []
  );

  const pause = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.pause();
      setIsPaused(true);
    }
  }, []);

  const resume = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.resume();
      setIsPaused(false);
    }
  }, []);

  const togglePause = useCallback(() => {
    if (isPaused) resume();
    else if (isSpeaking) pause();
  }, [isPaused, isSpeaking, pause, resume]);

  useEffect(() => {
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  return {
    speak,
    stop,
    pause,
    resume,
    togglePause,
    isSpeaking,
    isPaused,
    subtitle,
    setSubtitle,
  };
}
