import type { Activity, Trip } from "@/features/itinerary/domain/types";

export function buildWelcomeMessage(userName: string, trip: Trip): string {
  const dayCount = trip.days.length;
  return (
    `Namaste, ${userName}! I'm your AI tour guide for ${trip.destination}. ` +
    `I've analyzed your ${dayCount}-day itinerary and I'm ready to walk you through each day, ` +
    `starting with Day 1. Shall we begin?`
  );
}

export function buildDayOverview(trip: Trip, dayNumber: number): string {
  const day = trip.days.find((d) => d.dayNumber === dayNumber);
  if (!day) return "I couldn't find that day in your itinerary.";

  const activityCount = day.activities.length;
  const firstTitle = day.activities[0]?.title ?? "your first stop";

  const weatherNote = getWeatherAdjustmentNote(trip, dayNumber);

  return (
    `Today is ${day.title || `Day ${dayNumber}`} with ${activityCount} planned activities. ` +
    `We'll begin at ${firstTitle}. ${weatherNote}`
  );
}

export function buildActivityNarration(
  activity: Activity,
  index: number,
  total: number
): string {
  const parts: string[] = [
    `Stop ${index + 1} of ${total}: ${activity.title} at ${activity.time}.`,
  ];

  if (activity.description) {
    parts.push(activity.description);
  }

  if (activity.location) {
    parts.push(`Location: ${activity.location}.`);
  }

  if (activity.reason) {
    parts.push(activity.reason);
  }

  if (activity.estimatedCost > 0) {
    parts.push(`Estimated cost: around ${activity.estimatedCost}.`);
  }

  return parts.join(" ");
}

export function buildLandmarkNarration(
  landmarkName: string,
  historicalBackground: string
): string {
  return `I can see you're looking at ${landmarkName}. ${historicalBackground}`;
}

function getWeatherAdjustmentNote(trip: Trip, dayNumber: number): string {
  const constraints = trip.cognitiveTrace?.scif_pipeline?.weather_constraints ?? [];
  if (constraints.length === 0) return "";

  const relevant = constraints.find((c) =>
    c.toLowerCase().includes(`day ${dayNumber}`) || c.toLowerCase().includes("rain")
  );
  if (relevant) {
    return `Note: ${relevant}. I've adjusted outdoor activities accordingly.`;
  }
  return "";
}

export function formatTripDuration(trip: Trip): string {
  const days = trip.days.length;
  return `${days} Day${days !== 1 ? "s" : ""}`;
}
