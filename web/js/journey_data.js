// Offline fallbacks only: the demo boarding pass (when no photo is scanned), the demo profile (when
// the journey is opened without a trip card) and the demo papers list (when /api/visa/requirement
// is unreachable). Every scene calls the real backend first.

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
