"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Camera, Sparkles, Volume2, Info, MessageSquare, Upload, CircleDot, X } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { useAnalyzeLandmark, useAskLandmarkQA } from "@/features/explore/hooks/useExplore";

/** Strips the "data:image/jpeg;base64," prefix — the backend's base64.b64decode expects raw base64 only. */
function stripDataUrlPrefix(dataUrl: string): string {
  const commaIndex = dataUrl.indexOf(",");
  return commaIndex >= 0 ? dataUrl.slice(commaIndex + 1) : dataUrl;
}

export default function ExploreARPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-ink-400">Loading…</div>}>
      <ExploreARPageContent />
    </Suspense>
  );
}

function ExploreARPageContent() {
  const searchParams = useSearchParams();
  const [promptHint, setPromptHint] = useState(searchParams.get("hint") ?? "");
  const analyzeMutation = useAnalyzeLandmark();
  const askMutation = useAskLandmarkQA();

  const [question, setQuestion] = useState("");
  const [qaHistory, setQaHistory] = useState<string[]>([]);

  // Real camera capture state.
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [isCameraActive, setIsCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [capturedImageB64, setCapturedImageB64] = useState<string | null>(null);
  const [capturedPreviewUrl, setCapturedPreviewUrl] = useState<string | null>(null);

  const analysisResult = analyzeMutation.data;

  useEffect(() => {
    // Stop the camera stream on unmount so the browser's camera indicator
    // doesn't stay on after leaving the page.
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, []);

  const startCamera = async () => {
    setCameraError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
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

  const clearCapturedImage = () => {
    setCapturedImageB64(null);
    setCapturedPreviewUrl(null);
  };

  const handleAnalyze = () => {
    analyzeMutation.mutate({ promptHint, imageB64: capturedImageB64 ?? undefined });
  };

  const handleAsk = () => {
    if (!question || !analysisResult) return;
    askMutation.mutate(
      { landmarkName: analysisResult.landmark_name, question },
      {
        onSuccess: (data) => {
          setQaHistory((prev) => [...prev, `Q: ${data.question}\nA: ${data.answer}`]);
          setQuestion("");
        },
      }
    );
  };

  return (
    <div className="flex flex-col gap-6 p-6 max-w-7xl mx-auto w-full">
      <div>
        <h1 className="text-2xl font-bold font-display text-ink-900 dark:text-white flex items-center gap-2">
          <Camera className="h-6 w-6 text-brand-600" /> WebXR & Gemini Vision AR Explore Mode
        </h1>
        <p className="text-sm text-ink-500">
          Multimodal landmark identification, real-time WebXR overlay annotations, and historical audio narration
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* AR Viewfinder */}
        <div className="lg:col-span-7 flex flex-col gap-4">
          <div className="relative min-h-[420px] rounded-2xl overflow-hidden border border-ink-200 dark:border-ink-700 bg-ink-900 shadow-lg flex items-center justify-center text-white">
            {/* Live camera feed — hidden via CSS (not unmounted) while inactive so getUserMedia's stream stays attached correctly. */}
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
              <img src={capturedPreviewUrl} alt="Captured landmark" className="absolute inset-0 h-full w-full object-cover" />
            )}

            {!isCameraActive && !capturedPreviewUrl && (
              <div className="absolute inset-0 bg-[radial-gradient(#6366f1_1px,transparent_1px)] [background-size:24px_24px] opacity-25" />
            )}

            {analysisResult && (
              <div className="absolute top-4 left-4 right-4 bg-ink-950/85 backdrop-blur-md p-4 rounded-xl border border-ink-700 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-3 w-3 rounded-full bg-emerald-500 animate-ping" />
                  <div>
                    <h3 className="text-sm font-bold text-white">{analysisResult.landmark_name ?? "Not identified"}</h3>
                    <p className="text-xs text-ink-300">Confidence: {Math.round(analysisResult.confidence * 100)}%</p>
                  </div>
                </div>
                <span className="text-xs px-2.5 py-1 rounded-full bg-brand-500/20 text-brand-300 border border-brand-500/40 font-medium">
                  {analysisResult.category}
                </span>
              </div>
            )}

            {!isCameraActive && !capturedPreviewUrl && (
              <div className="relative z-10 flex flex-col items-center gap-3 text-center p-6 bg-ink-950/60 backdrop-blur-sm rounded-2xl border border-ink-800">
                <div className="h-20 w-20 rounded-full border-2 border-dashed border-brand-400 flex items-center justify-center text-brand-400">
                  <Camera className="h-10 w-10" />
                </div>
                <p className="text-xs text-ink-300">Start the camera or upload a photo to identify a landmark</p>
                {cameraError && <p className="text-xs text-sunset-400">{cameraError}</p>}
              </div>
            )}

            {capturedPreviewUrl && (
              <button
                onClick={clearCapturedImage}
                className="absolute top-4 right-4 rounded-full bg-ink-950/80 p-2 text-white hover:bg-ink-900"
                title="Remove photo"
              >
                <X className="h-4 w-4" />
              </button>
            )}

            <div className="absolute bottom-4 left-4 right-4 flex flex-wrap items-center justify-center gap-2">
              {isCameraActive ? (
                <>
                  <Button onClick={capturePhoto} className="flex items-center gap-2 shadow-lg">
                    <CircleDot className="h-4 w-4" /> Capture Photo
                  </Button>
                  <Button variant="outline" onClick={stopCamera}>
                    Cancel
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="outline" onClick={startCamera} className="flex items-center gap-2 shadow-lg">
                    <Camera className="h-4 w-4" /> Open Camera
                  </Button>
                  <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-ink-100 bg-white/90 px-4 py-2.5 text-sm font-medium text-ink-900 shadow-lg hover:bg-white dark:border-ink-700 dark:bg-ink-800/90 dark:text-white">
                    <Upload className="h-4 w-4" /> Upload Photo
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
                    onClick={handleAnalyze}
                    isLoading={analyzeMutation.isPending}
                    disabled={!capturedImageB64}
                    className="flex items-center gap-2 shadow-lg"
                  >
                    <Sparkles className="h-4 w-4" /> {analyzeMutation.isPending ? "Analyzing..." : "Identify Landmark"}
                  </Button>
                </>
              )}
            </div>
          </div>

          {analyzeMutation.isError && (
            <p className="text-sm text-sunset-600">{analyzeMutation.error.message}</p>
          )}

          <div className="flex items-center gap-3 bg-white dark:bg-ink-900 p-4 rounded-2xl border border-ink-100 dark:border-ink-700">
            <Input
              label="Optional hint (helps identification)"
              value={promptHint}
              onChange={(e) => setPromptHint(e.target.value)}
              placeholder="e.g. 'a stone cathedral' or the name if you know it"
            />
          </div>
        </div>

        {/* Knowledge & AR Overlay Sidebar */}
        <div className="lg:col-span-5 flex flex-col gap-4">
          <div className="bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700 shadow-sm flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-ink-900 dark:text-white flex items-center gap-2">
                <Info className="h-5 w-5 text-brand-600" /> Historical & Architectural Guide
              </h2>
              {analysisResult && (
                <button
                  onClick={() => {
                    if (typeof window !== "undefined" && "speechSynthesis" in window) {
                      const u = new SpeechSynthesisUtterance(analysisResult.historical_background);
                      window.speechSynthesis.speak(u);
                    }
                  }}
                  className="p-1.5 rounded-lg bg-brand-50 text-brand-600 dark:bg-brand-900/30 dark:text-brand-300 hover:opacity-80"
                  title="Play Audio Narration"
                >
                  <Volume2 className="h-4 w-4" />
                </button>
              )}
            </div>

            {!analysisResult ? (
              <p className="text-sm text-ink-400">
                No landmark analyzed yet — enter a hint and click Analyze, or point the camera at a monument.
              </p>
            ) : (
              <>
                <p className="text-xs leading-relaxed text-ink-700 dark:text-ink-300 bg-ink-50 dark:bg-ink-800 p-3 rounded-xl">
                  {analysisResult.historical_background || "No historical background available for this result."}
                </p>

                {analysisResult.architectural_highlights.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-ink-500 uppercase tracking-wider mb-2">Architectural Highlights</h3>
                    <ul className="list-disc list-inside text-xs text-ink-700 dark:text-ink-300 space-y-1">
                      {analysisResult.architectural_highlights.map((h: string, idx: number) => (
                        <li key={idx}>{h}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {analysisResult.photography_spots.length > 0 && (
                  <div>
                    <h3 className="text-xs font-semibold text-ink-500 uppercase tracking-wider mb-2">Photography Tips</h3>
                    <div className="flex flex-wrap gap-2">
                      {analysisResult.photography_spots.map((spot: string, idx: number) => (
                        <span key={idx} className="text-[11px] px-2.5 py-1 rounded-lg bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300 font-medium">
                          📸 {spot}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}

            <div className="border-t border-ink-100 dark:border-ink-800 pt-3">
              <h3 className="text-xs font-semibold text-ink-900 dark:text-white mb-2 flex items-center gap-1.5">
                <MessageSquare className="h-4 w-4 text-brand-600" /> Interactive AI Tour Guide Q&A
              </h3>
              <div className="flex gap-2">
                <Input
                  label="Ask Question"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder={analysisResult ? "Ask about this place..." : "Analyze a landmark first"}
                  disabled={!analysisResult}
                  className="text-xs"
                />
                <Button size="sm" onClick={handleAsk} isLoading={askMutation.isPending} disabled={!analysisResult}>
                  Ask
                </Button>
              </div>
              {qaHistory.length > 0 && (
                <div className="mt-3 flex flex-col gap-2 max-h-36 overflow-y-auto">
                  {qaHistory.map((ans, idx) => (
                    <div key={idx} className="p-2.5 rounded-lg bg-ink-50 dark:bg-ink-800 text-[11px] whitespace-pre-line text-ink-800 dark:text-ink-200">
                      {ans}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
