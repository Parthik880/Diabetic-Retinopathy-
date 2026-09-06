import { useState } from "react";

interface ImageComparisonProps {
  before: string;
  after: string;
  alt: string;
}

export function ImageComparison({ before, after, alt }: ImageComparisonProps) {
  const [position, setPosition] = useState(54);
  return (
    <div className="comparison">
      <img src={before} alt={`${alt}, before restoration`} />
      <div className="after-layer" style={{ clipPath: `inset(0 0 0 ${position}%)` }}>
        <img src={after} alt={`${alt}, after NAFNet restoration`} />
      </div>
      <div className="comparison-line" style={{ left: `${position}%` }} aria-hidden="true"><span /></div>
      <span className="comparison-label before">Before</span>
      <span className="comparison-label after">After</span>
      <input
        aria-label="Before and after comparison"
        type="range"
        min="0"
        max="100"
        value={position}
        onChange={(event) => setPosition(Number(event.target.value))}
      />
    </div>
  );
}
