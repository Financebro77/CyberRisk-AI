import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github-dark.css';
import { Copy, Check } from 'lucide-react';
import { useState } from 'react';

/** Copy button for code blocks. */
function CodeBlock({ className, children }: { className?: string; children?: React.ReactNode }) {
  const [copied, setCopied] = useState(false);
  const code = String(children ?? '');
  const copy = () => {
    void navigator.clipboard?.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="group relative">
      <button
        type="button"
        onClick={copy}
        className="absolute right-2 top-2 z-10 flex h-7 w-7 items-center justify-center rounded-md border border-white/10 bg-white/5 text-slate-400 opacity-0 transition-opacity hover:bg-white/10 group-hover:opacity-100"
        title="Copy code"
      >
        {copied ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
      <pre className={`overflow-x-auto rounded-lg bg-slate-950 p-3.5 text-[13px] leading-relaxed ${className ?? ''}`}>
        <code className="font-mono">{code}</code>
      </pre>
    </div>
  );
}

/**
 * Consultant markdown renderer: GFM (tables, lists, code) + syntax
 * highlighting.  Matches the consulting aesthetic — tables are bordered,
 * code blocks are dark with a copy button.
 */
export function ChatMarkdown({ content }: { content: string }) {
  return (
    <div className="chat-md text-[14.5px] leading-relaxed text-slate-800">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          h1: (props) => <h1 className="mb-3 mt-4 text-xl font-bold text-slate-900" {...props} />,
          h2: (props) => <h2 className="mb-2 mt-4 text-lg font-semibold text-slate-900" {...props} />,
          h3: (props) => <h3 className="mb-2 mt-3 text-base font-semibold text-slate-900" {...props} />,
          h4: (props) => <h4 className="mb-1.5 mt-3 text-sm font-semibold text-slate-800" {...props} />,
          p: (props) => <p className="my-2" {...props} />,
          ul: (props) => <ul className="my-2 list-disc space-y-1 pl-5" {...props} />,
          ol: (props) => <ol className="my-2 list-decimal space-y-1 pl-5" {...props} />,
          li: (props) => <li className="text-slate-800" {...props} />,
          blockquote: (props) => (
            <blockquote className="my-3 border-l-2 border-brand-300 bg-brand-50 px-4 py-2 text-slate-700" {...props} />
          ),
          a: (props) => <a className="text-accent underline hover:opacity-80" target="_blank" rel="noreferrer" {...props} />,
          code: ({ className, children, ...rest }) => {
            const match = /language-(\w+)/.exec(className ?? '');
            if (match) {
              return <CodeBlock className={className}>{children}</CodeBlock>;
            }
            return (
              <code
                className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[13px] text-brand-700"
                {...rest}
              >
                {children}
              </code>
            );
          },
          pre: ({ children }) => <>{children}</>,
          table: (props) => (
            <div className="my-3 overflow-x-auto rounded-lg border border-slate-200">
              <table className="min-w-full divide-y divide-slate-200 text-sm" {...props} />
            </div>
          ),
          thead: (props) => <thead className="bg-slate-50" {...props} />,
          th: (props) => <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500" {...props} />,
          td: (props) => <td className="px-3 py-2 text-slate-700" {...props} />,
          tr: (props) => <tr className="border-b border-slate-100 last:border-0" {...props} />,
          strong: (props) => <strong className="font-semibold text-slate-900" {...props} />,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
