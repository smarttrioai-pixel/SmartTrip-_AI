"use client";

import { useState } from "react";
import { Camera, Sparkles, Volume2, Info, Image as ImageIcon, MessageSquare, Compass, ShieldCheck } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";

export default function ExploreARPage() {
  const [promptHint, setPromptHint] = useState("Eiffel Tower Paris");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisResult, setAnalysisResult] = useState<any>({
    landmark_name: "Eiffel Tower",
    confidence: 0.98,
    category: "Architecture & History",
    historical_background: "Constructed in 1889 as the entrance arch for the Exposition Universelle (World's Fair), designed by engineer Gustave Eiffel.",
    architectural_highlights: ["324-meter wrought-iron lattice structure", "Puddle iron framework with 18,038 metallic parts"],
    cultural_importance: "Global cultural icon of France and one of the world's most recognizable architectural monuments.",
    photography_spots: ["Champ de Mars lawn at golden hour", "Trocadéro Plaza perspective"],
    nearby_attractions: ["Seine River Cruise", "Musée Quai Branly"],
  });
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<string[]>([]);

  const handleAnalyze = () => {
    setIsAnalyzing(true);
    setTimeout(() => {
      setIsAnalyzing(false);
    }, 1000);
  };

  const handleAsk = () => {
    if (!question) return;
    setAnswers([
      ...answers,
      `Q: ${question}\nA: ${analysisResult.landmark_name} holds immense significance in architectural history. ${analysisResult.historical_background}`,
    ]);
    setQuestion("");
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
        {/* AR Camera & Capture Feed */}
        <div className="lg:col-span-7 flex flex-col gap-4">
          <div className="relative min-h-[420px] rounded-2xl overflow-hidden border border-ink-200 dark:border-ink-700 bg-ink-900 shadow-lg flex items-center justify-center text-white">
            <div className="absolute inset-0 bg-[radial-gradient(#6366f1_1px,transparent_1px)] [background-size:24px_24px] opacity-25" />
            
            {/* Overlay AR Metadata Banner */}
            <div className="absolute top-4 left-4 right-4 bg-ink-950/85 backdrop-blur-md p-4 rounded-xl border border-ink-700 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-3 w-3 rounded-full bg-emerald-500 animate-ping" />
                <div>
                  <h3 className="text-sm font-bold text-white">{analysisResult.landmark_name}</h3>
                  <p className="text-xs text-ink-300">Match Confidence: {roundScore(analysisResult.confidence)}%</p>
                </div>
              </div>
              <span className="text-xs px-2.5 py-1 rounded-full bg-brand-500/20 text-brand-300 border border-brand-500/40 font-medium">
                {analysisResult.category}
              </span>
            </div>

            {/* Simulated Viewfinder Target */}
            <div className="relative z-10 flex flex-col items-center gap-3 text-center p-6 bg-ink-950/60 backdrop-blur-sm rounded-2xl border border-ink-800">
              <div className="h-20 w-20 rounded-full border-2 border-dashed border-brand-400 flex items-center justify-center text-brand-400 animate-spin-slow">
                <Compass className="h-10 w-10" />
              </div>
              <p className="text-xs text-ink-300">Point camera at any monument or upload a landmark photo</p>
            </div>

            {/* Bottom Controls Bar */}
            <div className="absolute bottom-4 left-4 right-4 flex items-center justify-center gap-3">
              <Button onClick={handleAnalyze} disabled={isAnalyzing} className="flex items-center gap-2 shadow-lg">
                <Sparkles className="h-4 w-4" /> {isAnalyzing ? "Analyzing Landmark..." : "Identify Landmark"}
              </Button>
            </div>
          </div>

          <div className="flex items-center gap-3 bg-white dark:bg-ink-900 p-4 rounded-2xl border border-ink-100 dark:border-ink-700">
            <Input
              value={promptHint}
              onChange={(e) => setPromptHint(e.target.value)}
              placeholder="Landmark name or hint..."
            />
            <Button variant="secondary" onClick={handleAnalyze}>
              Analyze
            </Button>
          </div>
        </div>

        {/* AI Knowledge & AR Overlay Sidebar */}
        <div className="lg:col-span-5 flex flex-col gap-4">
          <div className="bg-white dark:bg-ink-900 p-5 rounded-2xl border border-ink-100 dark:border-ink-700 shadow-sm flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-bold text-ink-900 dark:text-white flex items-center gap-2">
                <Info className="h-5 w-5 text-brand-600" /> Historical & Architectural Guide
              </h2>
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
            </div>

            <p className="text-xs leading-relaxed text-ink-700 dark:text-ink-300 bg-ink-50 dark:bg-ink-800 p-3 rounded-xl">
              {analysisResult.historical_background}
            </p>

            <div>
              <h3 className="text-xs font-semibold text-ink-500 uppercase tracking-wider mb-2">Architectural Highlights</h3>
              <ul className="list-disc list-inside text-xs text-ink-700 dark:text-ink-300 space-y-1">
                {analysisResult.architectural_highlights.map((h: string, idx: number) => (
                  <li key={idx}>{h}</li>
                ))}
              </ul>
            </div>

            <div>
              <h3 className="text-xs font-semibold text-ink-500 uppercase tracking-wider mb-2">Top Photography Spots</h3>
              <div className="flex flex-wrap gap-2">
                {analysisResult.photography_spots.map((spot: string, idx: number) => (
                  <span key={idx} className="text-[11px] px-2.5 py-1 rounded-lg bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300 font-medium">
                    📸 {spot}
                  </span>
                ))}
              </div>
            </div>

            <div className="border-t border-ink-100 dark:border-ink-800 pt-3">
              <h3 className="text-xs font-semibold text-ink-900 dark:text-white mb-2 flex items-center gap-1.5">
                <MessageSquare className="h-4 w-4 text-brand-600" /> Ask AI Tour Guide
              </h3>
              <div className="flex gap-2">
                <Input
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask about this place..."
                  className="text-xs"
                />
                <Button size="sm" onClick={handleAsk}>
                  Ask
                </Button>
              </div>
              {answers.length > 0 && (
                <div className="mt-3 flex flex-col gap-2 max-h-36 overflow-y-auto">
                  {answers.map((ans, idx) => (
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

function roundScore(val: number) {
  return Math.round(val * 100);
}
