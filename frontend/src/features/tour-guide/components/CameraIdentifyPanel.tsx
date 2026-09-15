"use client";

import { useEffect, useRef, useState } from "react";
import { Camera, CircleDot, Sparkles, Upload, X } from "lucide-react";

import { useAnalyzeLandmark } from "@/features/explore/hooks/useExplore";
import type { LandmarkAnalysisResult } from "@/features/explore/data/exploreApi";
import { Button } from "@/shared/components/ui/button";

function stripDataUrlPrefix(dataUrl: string): string {
  const commaIndex = dataUrl.indexOf(",");
  return commaIndex >= 0 ? dataUrl.slice(commaIndex + 1) : dataUrl;
}

interface CameraIdentifyPanelProps {
  open: boolean;
  onClose: () => void;
  onIdentified: (result: LandmarkAnalysisResult) => void;
  promptHint?: string;
}

export function CameraIdentifyPanel({
  open,
  onClose,
  onIdentified,
  promptHint = "",
}: CameraIdentifyPanelProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);

  const [isCameraActive, setIsCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [capturedImageB64, setCapturedImageB64] = useState<string | null>(null);
  const [capturedPreviewUrl, setCapturedPreviewUrl] = useState<string | null>(null);

  const analyzeMutation = useAnalyzeLandmark();

  useEffect(() => {
    if (!open) {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
      setIsCameraActive(false);
      setCapturedImageB64(null);
      setCapturedPreviewUrl(null);
      setCameraError(null);
    }
  }, [open]);

  useEffect(() => {
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  if (!open) return null;

  const startCamera = async () => {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment" },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setIsCameraActive(true);
    } catch {
      setCameraError("Camera access denied or unavailable. You can upload a photo instead.");
    }
  };

  const stopCamera = () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setIsCameraActive(false);
  };

  const capturePhoto = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;

    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const dataUrl = canvas.toDataURL("image/jpeg", 0.85);
    setCapturedPreviewUrl(dataUrl);
    setCapturedImageB64(stripDataUrlPrefix(dataUrl));
    stopCamera();
  };

  const handleFileUpload = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = reader.result as string;
      setCapturedPreviewUrl(dataUrl);
      setCapturedImageB64(stripDataUrlPrefix(dataUrl));
    };
    reader.readAsDataURL(file);
  };

  const handleAnalyze = () => {
    analyzeMutation.mutate(
      { promptHint, imageB64: capturedImageB64 ?? undefined },
      {
        onSuccess: (result) => {
          onIdentified(result);
        },
      }
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink-950/70 backdrop-blur-sm">
      <div className="relative w-full max-w-lg rounded-2xl border border-ink-700 bg-ink-900 shadow-2xl overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-ink-800">
          <h2 className="text-sm font-semibold text-white flex items-center gap-2">
            <Camera className="h-4 w-4 text-brand-400" />
            Identify what you&apos;re seeing
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-ink-400 hover:bg-ink-800 hover:text-white"
            aria-label="Close camera"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="relative aspect-[4/3] bg-ink-950">
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className={`absolute inset-0 h-full w-full object-cover ${isCameraActive ? "block" : "hidden"}`}
          />
          <canvas ref={canvasRef} className="hidden" />

          {!isCameraActive && capturedPreviewUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={capturedPreviewUrl}
              alt="Captured"
              className="absolute inset-0 h-full w-full object-cover"
            />
          )}

          {!isCameraActive && !capturedPreviewUrl && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center p-6">
              <div className="h-16 w-16 rounded-full border-2 border-dashed border-brand-400 flex items-center justify-center text-brand-400">
                <Camera className="h-8 w-8" />
              </div>
              <p className="text-xs text-ink-400">Tap Open Camera to start, then capture a photo</p>
              {cameraError && <p className="text-xs text-sunset-400">{cameraError}</p>}
            </div>
          )}
        </div>

        <div className="p-4 flex flex-wrap gap-2 justify-center border-t border-ink-800">
          {isCameraActive ? (
            <>
              <Button onClick={capturePhoto} size="sm" className="gap-2">
                <CircleDot className="h-4 w-4" /> Capture
              </Button>
              <Button variant="outline" size="sm" onClick={stopCamera}>
                Cancel
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" size="sm" onClick={startCamera} className="gap-2">
                <Camera className="h-4 w-4" /> Open Camera
              </Button>
              <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-ink-700 px-3 py-2 text-xs font-medium text-white hover:bg-ink-800">
                <Upload className="h-3.5 w-3.5" /> Upload
                <input
                  type="file"
                  accept="image/*"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleFileUpload(file);
                    e.target.value = "";
                  }}
                />
              </label>
              <Button
                size="sm"
                onClick={handleAnalyze}
                isLoading={analyzeMutation.isPending}
                disabled={!capturedImageB64}
                className="gap-2"
              >
                <Sparkles className="h-4 w-4" />
                {analyzeMutation.isPending ? "Analyzing…" : "Identify"}
              </Button>
            </>
          )}
        </div>

        {analyzeMutation.isError && (
          <p className="px-4 pb-4 text-xs text-sunset-400">{analyzeMutation.error.message}</p>
        )}
      </div>
    </div>
  );
}
