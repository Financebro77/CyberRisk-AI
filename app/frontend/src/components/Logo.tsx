import { ArmageddonMark } from './ArmageddonMark';

/** The Armageddon brand mark — the gold teardrop emblem from reference (6).png. */
export function Logo({ size = 32 }: { size?: number }) {
  return (
    <ArmageddonMark
      style={{ width: size, height: size * (781 / 860) }}
      ariaLabel="Armageddon"
    />
  );
}
