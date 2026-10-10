// Mock fixtures still used by the scenes that aren't wired to the real backend yet (check-in OCR,
// security/papers listing - see "How to work" step 2 in
// docs/FATHIMA_AIRPORT_EXPERIENCE_PROMPT.md). The desk, gate and outdoors scenes now call the real
// API (web/js/officer_api.js, web/js/desk.js) and no longer use mock data.

export const MOCK_PROFILE = {
  name: "Arjun Kumar",
  nationality: "IND",
  destination: "ARE",
};

export const MOCK_BOARDING_PASS = {
  name: "KUMAR/ARJUN",
  flight: "AI915",
  route: "COK to DXB",
  seat: "14C",
  date: "2026-10-11",
};

// Shown in the security scene, and as the papers list if the desk's documents_check stage (which
// returns the real list) is never reached - e.g. the visitor's own country, which skips straight
// to a verdict with no documents step.
export const MOCK_PAPERS = [
  { id: "return_ticket", label: "Return or onward ticket" },
  { id: "hotel_booking", label: "Hotel booking in your name" },
  { id: "funds_proof", label: "Proof of funds for your stay" },
];
