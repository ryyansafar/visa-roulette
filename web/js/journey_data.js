// Mock fixtures for the Airport Experience click-through. Shapes mirror the real API responses
// (see docs/FATHIMA_AIRPORT_EXPERIENCE_PROMPT.md section 4) so swapping to live fetches later is a
// render-function-only change, not a data-shape change.

export const MOCK_PROFILE = {
  name: "Arjun Kumar",
  nationality: "IND",
  destination: "ARE",
  destinationName: "United Arab Emirates",
};

export const MOCK_BOARDING_PASS = {
  name: "KUMAR/ARJUN",
  flight: "AI915",
  route: "COK to DXB",
  seat: "14C",
  date: "2026-10-11",
};

export const MOCK_STAMP = {
  status: "on_arrival",
  label: "Visa on arrival",
  note: "30 days on arrival for this passport.",
  source_url: "https://www.ica.gov.ae",
  as_of: "2026-10-11",
  verified: false,
};

export const MOCK_PAPERS = [
  { id: "return_ticket", label: "Return or onward ticket" },
  { id: "hotel_booking", label: "Hotel booking in your name" },
  { id: "funds_proof", label: "Proof of funds for your stay" },
];

// A scripted mock interview. Each step is one officer turn; `said` is the canned visitor reply that
// would trigger it for real via /api/officer/turn. stage "documents_check" pauses the script so the
// papers scene can run before the officer gives the verdict.
export const MOCK_PERSONA = { title: "Immigration Officer", strictness: 3, tone: "formal", voice: "en-gulf" };

export const MOCK_INTERVIEW = [
  { stage: "purpose", say: "Good day. Passport, please. May I ask the purpose of your visit?", said: "Tourism, five days." },
  { stage: "duration", say: "Thank you. How long do you intend to stay?", said: "Five days." },
  { stage: "accommodation", say: "I see. Where will you be staying during your visit?", said: "A hotel in Dubai Marina." },
  { stage: "funds_and_return", say: "Understood. Do you hold a return or onward ticket, and how will you fund your stay?", said: "Yes, return ticket booked, paying by card." },
  { stage: "documents_check", say: "Thank you. Please present your supporting documents.", said: null },
];

export const MOCK_VERDICT_LINE =
  "Thank you. Visa on arrival. 30 days on arrival for this passport. Source: ica.gov.ae, as of 2026-10-11. Demo rules, unverified.";

// Loaded live from the real fixture file (same shape the real /api/destination/{iso3} returns) -
// this keeps "mock data" honest to the actual contract instead of inventing a third shape.
export async function loadDestination() {
  const res = await fetch("/fixtures/destination.sample.json");
  return res.json();
}
