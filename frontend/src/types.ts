export type Role = "DONOR" | "NGO" | "VOLUNTEER" | "ADMIN";
export type Language = "en" | "kn" | "hi";
export type ListingStatus =
  | "DRAFT" | "PUBLISHED" | "MATCHED" | "ACCEPTED" | "PICKUP_ASSIGNED"
  | "PICKED_UP" | "DELIVERED" | "CANCELLED" | "EXPIRED" | "FLAGGED";
export type FoodCategory = "VEG" | "NON_VEG" | "EGG" | "MIXED";
export type Storage = "HOT_HELD" | "REFRIGERATED" | "ROOM_TEMPERATURE" | "FROZEN";

export interface User {
  id: number;
  email: string;
  full_name: string;
  phone: string | null;
  role: Role;
  preferred_language: Language;
  notify_in_app: boolean;
  notify_sms: boolean;
  is_active: boolean;
  is_demo: boolean;
  created_at: string;
}

export type Features = Record<string, boolean>;

export interface DonorProfile {
  id: number; organization_name: string; donor_type: string; address: string; area: string; latitude: number; longitude: number;
}

export interface NgoProfile {
  id: number; user_id: number; organization_name: string; registration_number: string; contact_person: string;
  address: string; area: string; latitude: number; longitude: number; service_radius_km: number;
  daily_capacity_portions: number; accepts_veg: boolean; accepts_non_veg: boolean; pickup_start_hour: number;
  pickup_end_hour: number; has_vehicle: boolean; verification_status: string; verification_notes: string | null;
  verified_at: string | null; created_at: string;
}

export interface VolunteerProfile {
  ngo_id: number; ngo_name: string; vehicle_type: string | null; area: string | null; is_available: boolean;
}

export interface Me {
  user: User;
  features: Features;
  donor_profile?: DonorProfile;
  ngo_profile?: NgoProfile;
  volunteer_profile?: VolunteerProfile;
}

export interface Match {
  ngo_id: number; ngo_name: string; ngo_area: string; rank: number; score: number; distance_km: number;
  components: Record<string, unknown>; explanation: string; decision: string | null;
}

export interface Listing {
  id: number; title: string; description: string | null; food_type: string; food_category: FoodCategory;
  portions_reported: number; prepared_at: string; pickup_deadline: string; storage_condition: Storage | null;
  packaging: string | null; allergens: string | null; area: string; latitude: number; longitude: number;
  location_precision: "exact" | "approximate"; pickup_address: string | null; donor_name: string | null;
  donor_phone: string | null; donor_organization: string | null; has_image: boolean; source: string;
  voice_transcript: string | null; voice_language: string | null; predicted_surplus_portions: number | null;
  status: ListingStatus; emergency: boolean; is_demo: boolean; accepted_ngo_id: number | null;
  accepted_ngo_name: string | null; published_at: string | null; accepted_at: string | null;
  created_at: string; updated_at: string; my_match: Match | null;
}

export interface SafetyIssue { code: string; severity: "BLOCKING" | "WARNING"; message: string }
export interface SafetyCheck {
  id: number; result: string; issues: SafetyIssue[]; review_decision: string | null; review_notes: string | null;
  reviewed_at: string | null; created_at: string;
}
export interface HistoryEntry {
  id: number; from_status: string | null; to_status: string; actor_name: string | null; actor_role: string | null;
  note: string | null; created_at: string;
}
export interface Assignment {
  id: number; listing_id: number; volunteer_id: number; volunteer_name: string; status: string;
  collected_portions: number | null; has_proof: boolean; collection_notes: string | null;
  picked_up_at: string | null; delivered_at: string | null; created_at: string;
}
export interface Delivery {
  collected_portions: number; delivered_portions: number; delivery_location: string | null; notes: string | null;
  receipt_number: string; ngo_acknowledged_at: string | null; created_at: string;
}
export interface ListingDetail extends Listing {
  history: HistoryEntry[]; safety_checks: SafetyCheck[]; matches: Match[]; assignment: Assignment | null;
  delivery: Delivery | null; safety_disclaimer: string; viewer_can: Record<string, boolean>;
}
export interface PublishResult {
  listing: ListingDetail; safety_result: string; issues: SafetyIssue[]; matches_found: number; message: string;
}

export interface VoiceDraft {
  title?: string | null; food_type?: string | null; food_category?: FoodCategory | null; portions_reported?: number | null;
  prepared_at?: string | null; pickup_deadline?: string | null; storage_condition?: Storage | null; allergens?: string | null;
  area?: string | null; latitude?: number | null; longitude?: number | null;
}
export interface VoiceResult {
  simulated: boolean; mode: string; language: string; transcript: string; english_text: string; draft: VoiceDraft;
  missing_fields: string[]; notes: string[]; extraction_method: string;
}

export interface Notification {
  id: number; listing_id: number | null; type: string; channel: string; language: string; title: string; body: string;
  original_body: string | null; translation_source: string | null; status: string; error: string | null;
  created_at: string; read_at: string | null;
}

export interface VolunteerOption {
  user_id: number; full_name: string; phone: string | null; vehicle_type: string | null; area: string | null;
  is_available: boolean; active_assignments: number;
}

export interface VolunteerAssignment {
  assignment_id: number; assignment_status: string; collected_portions: number | null; picked_up_at: string | null;
  delivered_at: string | null; ngo_name: string; ngo_address: string; ngo_latitude: number; ngo_longitude: number;
  listing: Listing;
}

export interface Prediction {
  is_prediction: boolean; label: string; method: string; predicted_surplus_portions: number; range_low: number;
  range_high: number; assumptions: string[]; [k: string]: unknown;
}

export interface Impact {
  reported_portions: number; collected_portions: number; delivered_portions: number; completed_donations: number;
  average_matching_minutes: number | null; collection_success_rate: number | null; predicted_surplus_portions: number;
  verified_ngos: number; definitions: Record<string, string>; includes_demo_data: boolean;
  delivered_by_day: { date: string; portions: number }[]; delivered_by_category: { category: string; portions: number }[];
  enabled?: boolean;
}

export interface FlagRow {
  name: string; description: string; enabled: boolean; source: string; default: boolean;
  flagsmith_value: boolean | null; local_override: boolean | null;
}

export interface Incident {
  id: number; category: string; severity: string; title: string; details: Record<string, unknown>; status: string;
  occurrences: number; first_seen: string; last_seen: string; resolved_at: string | null;
}
