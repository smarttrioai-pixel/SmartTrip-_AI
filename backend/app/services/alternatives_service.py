import logging
import asyncio
from typing import Any

from app.schemas.trip import ActivityAlternative
from app.cognitive.recommendation_engine import RecommendationEngine
from app.cognitive.memory_engine import MemoryEngine
from app.services.llm_service import LLMService
from app.services.place_enrichment_service import PlaceEnrichmentService

logger = logging.getLogger(__name__)

class AlternativeRecommendationService:
    def __init__(
        self,
        place_enrichment_service: PlaceEnrichmentService,
        recommendation_engine: RecommendationEngine,
        memory_engine: MemoryEngine,
        llm_service: LLMService,
    ) -> None:
        self._place_enrichment = place_enrichment_service
        self._recommendation = recommendation_engine
        self._memory = memory_engine
        self._llm = llm_service

    async def get_alternatives(
        self,
        activity: dict,
        trip: dict,
        user_id: str,
        limit: int = 3,
    ) -> list[ActivityAlternative]:
        try:
            # 1. Extract lat/lon from activity or trip destination
            lat = None
            lon = None
            if "place_enrichment" in activity and activity["place_enrichment"]:
                lat = activity["place_enrichment"].get("lat")
                lon = activity["place_enrichment"].get("lon")

            destination = trip.get("destination", "")
            if lat is None or lon is None:
                geo = await self._place_enrichment._resolve_destination_coords(destination)
                if geo:
                    lat = geo["lat"]
                    lon = geo["lon"]
            
            if lat is None or lon is None:
                logger.warning("Could not resolve coordinates for alternatives.")
                return []

            # 2. Determine place type from activity category
            category = (activity.get("category") or "").lower()
            if category == "transport":
                return []

            # 3. Search nearby places
            candidates = []
            
            title = activity.get("title", "")
            enrichment = activity.get("place_enrichment") or {}
            current_place_id = enrichment.get("place_id") or activity.get("place_id")

            if category in ["meal", "restaurant", "cafe"]:
                is_meal = True
                if self._place_enrichment._google_enabled:
                    try:
                        cands = await self._place_enrichment._google.search_restaurants(
                            lat=lat, lon=lon, food_query=f"restaurant in {destination}", radius_m=15000, limit=20
                        )
                        candidates.extend(cands)
                    except Exception as e:
                        logger.warning(f"Google meal search failed: {e}")
                
                if not candidates and self._place_enrichment._geoapify_fallback_enabled:
                    try:
                        from app.integrations.geoapify_provider import CATEGORY_MAP
                        cands = await self._place_enrichment._geoapify.search_places(
                            latitude=lat, longitude=lon, categories=CATEGORY_MAP.get("meal", ["catering.restaurant"]), radius_meters=15000, limit=20
                        )
                        candidates.extend([c for c in cands if c.get("place_id")])
                    except Exception as e:
                        logger.warning(f"Geoapify meal search failed: {e}")
            else:
                is_meal = False
                query_cat = "tourist attractions"
                if category in ["attraction", "culture", "museum", "sights"]:
                    query_cat = category
                elif category == "nature":
                    query_cat = "park"
                
                if self._place_enrichment._google_enabled:
                    try:
                        cands = await self._place_enrichment._google.search_attractions(
                            lat=lat, lon=lon, query=f"{query_cat} in {destination}", radius_m=15000, limit=20
                        )
                        candidates.extend(cands)
                    except Exception as e:
                        logger.warning(f"Google attraction search failed: {e}")
                
                if not candidates and self._place_enrichment._geoapify_fallback_enabled:
                    try:
                        from app.integrations.geoapify_provider import GeoapifyProvider
                        cands = await self._place_enrichment._geoapify.search_places(
                            latitude=lat, longitude=lon, categories=GeoapifyProvider.categories_for_concept(category), radius_meters=15000, limit=20
                        )
                        candidates.extend([c for c in cands if c.get("place_id")])
                    except Exception as e:
                        logger.warning(f"Geoapify attraction search failed: {e}")

            # Normalize and filter candidates
            normalized = []
            for c in candidates:
                # Handle both PlaceCandidate (Google) and dict (Geoapify)
                place_id = getattr(c, "place_id", None) or c.get("place_id") if isinstance(c, dict) else None
                name = getattr(c, "name", None) or c.get("name") if isinstance(c, dict) else ""
                dist = getattr(c, "distance_m", None) or c.get("distance_m") if isinstance(c, dict) else 0
                status = getattr(c, "business_status", None) or c.get("business_status") if isinstance(c, dict) else None
                
                # 4. Filter: exclude current activity, closed places, too far
                if place_id == current_place_id or name.lower() == title.lower():
                    continue
                if status == "CLOSED_PERMANENTLY" or status == "CLOSED_TEMPORARILY":
                    continue
                if dist and dist > 15000:
                    continue
                
                act_dict = {
                    "place_id": place_id,
                    "title": name,
                    "description": "",
                    "category": category,
                    "location": getattr(c, "address", None) or (c.get("address") if isinstance(c, dict) else ""),
                    "lat": getattr(c, "lat", None) or (c.get("lat") if isinstance(c, dict) else lat),
                    "lon": getattr(c, "lon", None) or (c.get("lon") if isinstance(c, dict) else lon),
                    "distance_meters": int(dist) if dist else None,
                    "rating": getattr(c, "rating", None) or (c.get("rating") if isinstance(c, dict) else None),
                    "estimated_cost": getattr(c, "price_level", 0) * 15.0 if getattr(c, "price_level", None) else 0.0,
                    "opening_status": status
                }
                # To score, the RecommendationEngine expects some fields
                act_dict["place_enrichment"] = act_dict.copy()
                normalized.append(act_dict)

            # Deduplicate
            seen = set()
            unique_cands = []
            for n in normalized:
                if n["place_id"] not in seen:
                    seen.add(n["place_id"])
                    unique_cands.append(n)

            # 5. Get user behavioral weights
            try:
                mem_context = await self._memory.get_context(user_id, "")
                weights = mem_context.feature_weights
            except Exception:
                weights = {}

            # 6. Score using RecommendationEngine
            daily_budget = float(trip.get("budget", 100)) / max(1, len(trip.get("days", [])))
            # RecommendationEngine expects preferences object, create mock
            from app.models.user import UserPreferences
            prefs = UserPreferences(interests=[])
            
            scored = await self._recommendation.score_and_rank(
                activities=unique_cands,
                preferences=prefs,
                daily_budget_hint=daily_budget,
                destination_lat=lat,
                destination_lon=lon,
                feature_weights=weights
            )

            # 7. Take top `limit` candidates
            top_scored = scored[:limit]

            # 8. Call OpenAI to produce reason
            results = []
            for sc in top_scored:
                act = sc.activity
                sys_prompt = "You are a travel assistant explaining why an alternative activity is a good fit."
                user_prompt = f"The user originally planned to visit '{title}' but wants an alternative. We recommend '{act['title']}'. In 1-2 short sentences, explain why this is a good alternative for them."
                
                try:
                    reason = await self._llm.generate(sys_prompt, user_prompt, max_tokens=100)
                except Exception:
                    reason = f"A great alternative {category} to consider in the area."
                
                results.append(ActivityAlternative(
                    place_id=act["place_id"],
                    title=act["title"],
                    description=f"Alternative to {title}",
                    category=act["category"],
                    location=act["location"],
                    lat=act["lat"],
                    lon=act["lon"],
                    distance_meters=act["distance_meters"],
                    estimated_cost=act["estimated_cost"],
                    rating=act["rating"],
                    opening_status=act["opening_status"],
                    reason=reason.strip().replace('"', ''),
                    preference_match=round(sc.composite_score, 2)
                ))

            return results
        except Exception as e:
            logger.error(f"Error getting alternatives: {e}")
            return []
