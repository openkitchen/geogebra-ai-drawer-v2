interface WelcomeScreenProps {
  onSuggestionClick: (text: string, intentHint?: Record<string, unknown>) => void;
}

export function WelcomeScreen({ onSuggestionClick }: WelcomeScreenProps) {
  const suggestions: Array<{ text: string; intentHint?: Record<string, unknown> }> = [
    { text: "Draw a circle with radius 3 at (0,0)", intentHint: { wants_draw: true, wants_circle: true } },
    { text: "Plot y = sin(x)", intentHint: { wants_draw: true } },
    { text: "Draw a triangle ABC", intentHint: { wants_draw: true, wants_triangle: true } },
    { text: "Construct the perpendicular bisector of AB", intentHint: { wants_draw: true } },
  ];

  return (
    <div className="welcome-screen">
      <div className="welcome-icon">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M8 14s1.5 2 4 2 4-2 4-2"></path>
          <line x1="9" y1="9" x2="9.01" y2="9"></line>
          <line x1="15" y1="9" x2="15.01" y2="9"></line>
        </svg>
      </div>
      <h3>Welcome to GeoGebra AI</h3>
      <p style={{ marginTop: 8, maxWidth: 320, lineHeight: 1.5 }}>
        I can help you draw geometric shapes and functions. 
        Just describe what you want to see!
      </p>

      <div className="suggestion-grid">
        {suggestions.map((s, i) => (
          <button 
            key={i} 
            className="suggestion-chip"
            onClick={() => onSuggestionClick(s.text, s.intentHint)}
          >
            {s.text}
          </button>
        ))}
      </div>
    </div>
  );
}

