import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Send, X } from 'lucide-react';
import { api } from '@/lib/api';

// ─── Types ────────────────────────────────────────────────────────────────────

type Role = 'user' | 'assistant';

interface Message {
  id: string;
  role: Role;
  content: string;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const SUGGESTED_PROMPTS = [
  'What happened in my portfolio today?',
  'Summarise RELIANCE latest results',
  'How has INFY guidance held up?',
];

// ─── Markdown Renderer ────────────────────────────────────────────────────────

function renderMarkdown(text: string): React.ReactNode {
  return text.split('\n').map((line, i) => {
    const trimmed = line.trim();

    if (!trimmed) return <div key={i} className="h-1.5" />;

    // Bold header: **text**
    if (/^\*\*(.+)\*\*$/.test(trimmed)) {
      return (
        <p key={i} className="text-xs font-bold text-white mt-2 mb-0.5">
          {trimmed.replace(/\*\*/g, '')}
        </p>
      );
    }

    // Bullet: - or •
    if (/^[-•]/.test(trimmed)) {
      const content = trimmed.replace(/^[-•]\s*/, '');
      const parts = content.split(/(\*\*[^*]+\*\*)/g);
      return (
        <div key={i} className="flex gap-1.5 text-[13px] text-[#CBD5E1] leading-relaxed">
          <span className="text-[#3B82F6] mt-0.5 flex-shrink-0">•</span>
          <span>
            {parts.map((part, j) =>
              /^\*\*(.+)\*\*$/.test(part) ? (
                <strong key={j} className="text-white font-semibold">
                  {part.replace(/\*\*/g, '')}
                </strong>
              ) : (
                part
              )
            )}
          </span>
        </div>
      );
    }

    // Regular line
    const parts = trimmed.split(/(\*\*[^*]+\*\*)/g);
    return (
      <p key={i} className="text-[13px] text-[#CBD5E1] leading-relaxed">
        {parts.map((part, j) =>
          /^\*\*(.+)\*\*$/.test(part) ? (
            <strong key={j} className="text-white font-semibold">
              {part.replace(/\*\*/g, '')}
            </strong>
          ) : (
            part
          )
        )}
      </p>
    );
  });
}

// ─── Typing Indicator ─────────────────────────────────────────────────────────

const TypingIndicator: React.FC = () => (
  <div className="flex items-end gap-2">
    {/* Avatar */}
    <div className="w-7 h-7 rounded-full bg-[#3B82F6] flex items-center justify-center flex-shrink-0">
      <span className="text-[10px] font-black text-white">F</span>
    </div>
    <div className="flex items-center gap-1.5 bg-[#1E293B] rounded-2xl rounded-bl-sm px-4 py-3">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-[#64748B] animate-bounce"
          style={{ animationDelay: `${i * 150}ms`, animationDuration: '900ms' }}
        />
      ))}
    </div>
  </div>
);

// ─── Message Bubble ───────────────────────────────────────────────────────────

const MessageBubble: React.FC<{ message: Message }> = ({ message }) => {
  const isUser = message.role === 'user';

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] bg-[#3B82F6] rounded-2xl rounded-br-sm px-4 py-2.5">
          <p className="text-[13px] text-white leading-relaxed">{message.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-end gap-2">
      {/* FINN Avatar */}
      <div className="w-7 h-7 rounded-full bg-[#3B82F6] flex items-center justify-center flex-shrink-0 mb-0.5">
        <span className="text-[10px] font-black text-white">F</span>
      </div>
      <div className="max-w-[80%] bg-[#1E293B] rounded-2xl rounded-bl-sm px-4 py-3">
        <div className="space-y-0.5">{renderMarkdown(message.content)}</div>
      </div>
    </div>
  );
};

// ─── Welcome State ────────────────────────────────────────────────────────────

const WelcomeState: React.FC<{ onPrompt: (prompt: string) => void }> = ({ onPrompt }) => (
  <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 text-center gap-6">
    <div className="w-14 h-14 rounded-full bg-[#3B82F6] flex items-center justify-center">
      <span className="text-xl font-black text-white">F</span>
    </div>
    <div>
      <p className="text-base font-bold text-white mb-1">Ask me anything</p>
      <p className="text-sm text-[#64748B]">about your portfolio</p>
    </div>
    <div className="w-full space-y-2">
      {SUGGESTED_PROMPTS.map((prompt) => (
        <button
          key={prompt}
          onClick={() => onPrompt(prompt)}
          className="w-full text-left px-4 py-3 rounded-xl bg-[#1E293B] text-sm text-[#CBD5E1] hover:bg-[#263548] hover:text-white transition-colors border border-[#263548] hover:border-[#3B82F6]/40"
        >
          {prompt}
        </button>
      ))}
    </div>
  </div>
);

// ─── Main Screen ──────────────────────────────────────────────────────────────

const ChatScreen: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const ticker = searchParams.get('ticker')?.toUpperCase() ?? null;

  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Pre-populate from context param
  useEffect(() => {
    const context = searchParams.get('context');
    if (context && messages.length === 0) {
      setInput(`Tell me more about: ${decodeURIComponent(context)}`);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isTyping]);

  const sendMessage = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || isTyping) return;

      const userMsg: Message = {
        id: `u-${Date.now()}`,
        role: 'user',
        content: trimmed,
      };

      setMessages((prev) => [...prev, userMsg]);
      setInput('');
      setIsTyping(true);

      try {
        const apiMessages = [...messages, userMsg].map((m) => ({
          role: m.role,
          content: m.content,
        }));
        const response = await api.chat(apiMessages, ticker ?? undefined);
        const assistantMsg: Message = {
          id: `a-${Date.now()}`,
          role: 'assistant',
          content: response?.response ?? 'Sorry, I was unable to generate a response.',
        };
        setMessages((prev) => [...prev, assistantMsg]);
      } catch {
        const errMsg: Message = {
          id: `a-err-${Date.now()}`,
          role: 'assistant',
          content: 'Something went wrong. Please try again.',
        };
        setMessages((prev) => [...prev, errMsg]);
      } finally {
        setIsTyping(false);
      }
    },
    [messages, isTyping, ticker]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const clearTicker = () => {
    setSearchParams({});
  };

  return (
    <div className="h-screen bg-[#0F172A] max-w-[430px] mx-auto flex flex-col">
      {/* Header */}
      <header className="flex-shrink-0 bg-[#0F172A]/95 backdrop-blur border-b border-[#1E293B] px-4 py-3">
        <span className="text-base font-black tracking-tight text-white">FINN</span>
        <span className="text-xs text-[#64748B] ml-2">Chat</span>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 && !isTyping ? (
          <WelcomeState onPrompt={(p) => sendMessage(p)} />
        ) : (
          <div className="px-4 py-4 space-y-4">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            {isTyping && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="flex-shrink-0 bg-[#0F172A] border-t border-[#1E293B] px-4 pt-3 pb-4">
        {/* Context badge */}
        {ticker && (
          <div className="flex items-center gap-2 mb-2">
            <span className="flex items-center gap-1.5 text-[11px] font-semibold text-[#3B82F6] bg-[#3B82F6]/10 border border-[#3B82F6]/30 rounded-full px-2.5 py-0.5">
              Context: {ticker}
              <button onClick={clearTicker} className="hover:text-white transition-colors ml-0.5">
                <X size={10} />
              </button>
            </span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask FINN anything..."
            rows={1}
            className="flex-1 bg-[#1E293B] text-sm text-white placeholder-[#475569] px-3 py-2.5 rounded-xl outline-none border border-transparent focus:border-[#3B82F6] transition-colors resize-none max-h-32 overflow-y-auto leading-relaxed"
            style={{ fieldSizing: 'content' } as React.CSSProperties}
          />
          <button
            type="submit"
            disabled={!input.trim() || isTyping}
            className="flex-shrink-0 w-10 h-10 bg-[#3B82F6] rounded-xl flex items-center justify-center disabled:opacity-40 transition-opacity hover:bg-[#2563EB]"
          >
            <Send size={16} className="text-white" />
          </button>
        </form>
        <p className="text-[10px] text-[#334155] mt-1.5 text-center">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
};

export default ChatScreen;
