import { useEffect, useRef, type ReactNode } from 'react';

interface RevealProps {
  children: ReactNode;
  /** Add `reveal-stagger` to fade children in sequence. */
  stagger?: boolean;
  className?: string;
  as?: 'div' | 'section' | 'li';
}

/**
 * Scroll-reveal wrapper.  Elements start invisible and fade up once they
 * enter the viewport.  Respects prefers-reduced-motion via CSS.
 */
export function Reveal({ children, stagger = false, className = '', as = 'div' }: RevealProps) {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: '0px 0px -40px 0px' },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const Tag = as;
  return (
    <Tag
      ref={ref as never}
      className={`reveal ${stagger ? 'reveal-stagger' : ''} ${className}`}
    >
      {children}
    </Tag>
  );
}
