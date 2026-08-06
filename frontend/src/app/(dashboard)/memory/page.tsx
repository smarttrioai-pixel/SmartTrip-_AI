"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Brain, Plus } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { useMemoryInsights, useSavePreference } from "@/features/memory/hooks/useMemory";
import { FeatureWeightBar } from "@/features/memory/components/FeatureWeightBar";
import { InferredPreferenceCard } from "@/features/memory/components/InferredPreferenceCard";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";

const addPreferenceSchema = z.object({ text: z.string().min(2, "Tell us a bit more") });
type AddPreferenceValues = z.infer<typeof addPreferenceSchema>;

export default function MemoryPage() {
  const { data: insights, isLoading } = useMemoryInsights();
  const savePreference = useSavePreference();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AddPreferenceValues>({ resolver: zodResolver(addPreferenceSchema) });

  const onSubmit = (values: AddPreferenceValues) =>
    savePreference.mutate(values.text, { onSuccess: () => reset() });

  const activeWeights = insights
    ? Object.entries(insights.featureWeights).filter(([, v]) => Math.abs(v) > 0.05)
    : [];

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <div className="flex items-center gap-3">
        <Brain className="h-6 w-6 text-brand-500" />
        <h1 className="font-display text-2xl font-semibold text-ink-900 dark:text-white">
          What SmartTrip has learned about you
        </h1>
      </div>
      <p className="mt-1 text-sm text-ink-400">
        These preferences shape your itineraries. Nothing here is fixed — reject anything that's
        off, and add anything we've missed.
      </p>

      {isLoading && <p className="mt-8 text-sm text-ink-400">Loading…</p>}

      {insights && (
        <div className="mt-8 flex flex-col gap-8">
          <section>
            <h2 className="mb-3 font-display text-lg font-semibold text-ink-900 dark:text-white">
              Learned tendencies
            </h2>
            {activeWeights.length === 0 ? (
              <p className="rounded-xl border border-dashed border-ink-100 p-6 text-center text-sm text-ink-400 dark:border-ink-700">
                Not enough activity yet — accept or save a few trips and this will fill in.
              </p>
            ) : (
              <div className="flex flex-col gap-3 rounded-2xl border border-ink-100 bg-white p-5 dark:border-ink-700 dark:bg-ink-800">
                {activeWeights.map(([feature, value]) => (
                  <FeatureWeightBar key={feature} feature={feature} value={value} />
                ))}
              </div>
            )}
          </section>

          <section>
            <h2 className="mb-3 font-display text-lg font-semibold text-ink-900 dark:text-white">
              Inferred preferences
            </h2>
            {insights.inferredPreferences.length === 0 ? (
              <p className="rounded-xl border border-dashed border-ink-100 p-6 text-center text-sm text-ink-400 dark:border-ink-700">
                No confident patterns yet — these appear after enough consistent trip activity.
              </p>
            ) : (
              <div className="flex flex-col gap-2">
                {insights.inferredPreferences.map((inference) => (
                  <InferredPreferenceCard key={inference.id} inference={inference} />
                ))}
              </div>
            )}
          </section>

          <section>
            <h2 className="mb-3 font-display text-lg font-semibold text-ink-900 dark:text-white">
              Saved preferences
            </h2>
            <form onSubmit={handleSubmit(onSubmit)} className="mb-4 flex gap-2" noValidate>
              <div className="flex-1">
                <Input
                  label=""
                  placeholder="e.g. I love quiet beach towns over big cities"
                  error={errors.text?.message}
                  {...register("text")}
                />
              </div>
              <Button type="submit" isLoading={savePreference.isPending}>
                <Plus className="h-4 w-4" /> Add
              </Button>
            </form>

            {insights.preferences.length === 0 ? (
              <p className="rounded-xl border border-dashed border-ink-100 p-6 text-center text-sm text-ink-400 dark:border-ink-700">
                No saved preferences yet.
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {insights.preferences.map((pref) => (
                  <li
                    key={pref.id}
                    className="rounded-xl border border-ink-100 bg-white px-4 py-3 text-sm text-ink-900 dark:border-ink-700 dark:bg-ink-800 dark:text-white"
                  >
                    {pref.sourceText}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
