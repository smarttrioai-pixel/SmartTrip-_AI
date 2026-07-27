"use client";

import { useState } from "react";
import { Camera, Sparkles, Volume2, Info, MessageSquare, Compass } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { useAnalyzeLandmark, useAskLandmarkQA } from "@/features/explore/hooks/useExplore";

export default function ExploreARPage() {
  const [promptHint, setPromptHint] = useState("");
  const analyzeMutation = useAnalyzeLandmark();
  const askMutation = useAskLandmarkQA();

  const [question, setQuestion] = useState("");
  const [qaHistory, setQaHistory] = useState<string[]>([]);

  const analysisResult = analyzeMutation.data;

  const handleAnalyze = () => {
    analyzeMutation.mutate({ promptHint });
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
            <div className="absolute inset-0 bg-[radial-gradient(#6366f1_1px,transparent_1px)] [background-size:24px_24px] opacity-25" />

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

            <div className="relative z-10 flex flex-col items-center gap-3 text-center p-6 bg-ink-950/60 backdrop-blur-sm rounded-2xl border border-ink-800">
              <div className="h-20 w-20 rounded-full border-2 border-dashed border-brand-400 flex items-center justify-center text-brand-400">
                <Compass className="h-10 w-10" />
              </div>
              <p className="text-xs text-ink-300">Point camera at any monument or enter landmark hint</p>
            </div>

            <div className="absolute bottom-4 left-4 right-4 flex items-center justify-center gap-3">
              <Button onClick={handleAnalyze} isLoading={analyzeMutation.isPending} className="flex items-center gap-2 shadow-lg">
                <Sparkles className="h-4 w-4" /> {analyzeMutation.isPending ? "Analyzing..." : "Identify Landmark"}
              </Button>
            </div>
          </div>

          {analyzeMutation.isError && (
            <p className="text-sm text-sunset-600">{analyzeMutation.error.message}</p>
          )}

          <div className="flex items-center gap-3 bg-white dark:bg-ink-900 p-4 rounded-2xl border border-ink-100 dark:border-ink-700">
            <Input
              label="Landmark Search Hint"
              value={promptHint}
              onChange={(e) => setPromptHint(e.target.value)}
              placeholder="Enter landmark name or hint..."
            />
            <Button variant="outline" onClick={handleAnalyze} isLoading={analyzeMutation.isPending}>
              Analyze
            </Button>
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
