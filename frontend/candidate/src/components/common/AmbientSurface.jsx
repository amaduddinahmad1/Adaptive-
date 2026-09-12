import React from 'react';

const MOTIF_HEIGHTS = [
  10, 16, 12, 22, 34, 48, 38, 56, 28, 44, 62, 36, 18, 14, 10, 12, 24, 40, 52, 32,
  58, 46, 22, 16, 28, 38, 20, 12, 10,
];

const WaveformMotif = () => (
  <svg
    className="absolute left-1/2 top-0 w-[min(36rem,118%)] -translate-x-1/2 -translate-y-[22%] text-text opacity-[0.07]"
    viewBox="0 0 406 80"
    fill="currentColor"
    aria-hidden="true"
  >
    {MOTIF_HEIGHTS.map((height, index) => (
      <rect
        key={index}
        x={index * 14}
        y={72 - height}
        width="3.5"
        height={height}
        rx="1.75"
      />
    ))}
  </svg>
);

const AmbientSurface = ({ variant = 'heading' }) => (
  <div className="pointer-events-none absolute inset-0 overflow-visible" aria-hidden="true">
    <div
      className={
        variant === 'stage' ? 'ambient-glow ambient-glow--stage' : 'ambient-glow ambient-glow--heading'
      }
    />
    {variant === 'heading' ? <WaveformMotif /> : null}
  </div>
);

export default AmbientSurface;
