import { useEffect, useRef } from 'react';

/**
 * Ambient falling-glyph rain for the hero.  Deliberately subtle — slow, low
 * opacity, mostly cyan with occasional green — so the headline stays the
 * focus.  Renders nothing where a 2d context is unavailable (jsdom, no GPU)
 * or reduced motion is requested, and pauses while the tab is hidden.
 */
export function MatrixRain({ className }: { className?: string }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    if (document.hidden) return;
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;

    let ctx: CanvasRenderingContext2D | null = null;
    try {
      ctx = canvas.getContext('2d');
    } catch {
      /* no canvas in this environment */
    }
    if (!ctx) return;

    const GLYPHS = '01アカサタナハマヤラワ0123456789ABCDEF';
    const fontSize = 14;
    let cols = 0;
    let drops: number[] = [];
    let raf = 0;
    let width = 0;
    let height = 0;

    const resize = () => {
      const parent = canvas.parentElement;
      if (!parent) return;
      width = parent.clientWidth;
      height = parent.clientHeight;
      canvas.width = width;
      canvas.height = height;
      cols = Math.ceil(width / fontSize);
      drops = Array.from({ length: cols }, () => Math.floor((Math.random() * -height) / fontSize));
    };

    const tick = () => {
      // Fade the previous frame toward the hero black, then drop one glyph per
      // column.  ~12% of drops are signal green; the rest cyan.
      ctx.fillStyle = 'rgba(2, 4, 9, 0.18)';
      ctx.fillRect(0, 0, width, height);
      ctx.font = `${fontSize}px "Geist Mono", monospace`;
      for (let i = 0; i < cols; i++) {
        const ch = GLYPHS[Math.floor(Math.random() * GLYPHS.length)];
        ctx.fillStyle =
          Math.random() < 0.12 ? 'rgba(74, 222, 128, 0.30)' : 'rgba(34, 211, 238, 0.30)';
        const y = drops[i] * fontSize;
        ctx.fillText(ch, i * fontSize, y);
        if (y > height && Math.random() > 0.975) drops[i] = 0;
        drops[i]++;
      }
      raf = requestAnimationFrame(tick);
    };

    resize();
    tick();

    const onVisibility = () => {
      cancelAnimationFrame(raf);
      if (!document.hidden) {
        ctx.clearRect(0, 0, width, height);
        tick();
      }
    };
    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('resize', resize);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return <canvas ref={ref} className={className} aria-hidden="true" />;
}
