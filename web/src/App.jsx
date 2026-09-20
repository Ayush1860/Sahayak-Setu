import { useEffect, useRef, useState } from "react";
import { ask } from "./api";

const COPY = {
  hi: {
    title: "सहायक सेतु",
    tagline: "अपना काम बताइए। हम बताएँगे कौन सी सरकारी योजना आपके लिए हो सकती है।",
    placeholder: "जैसे: मैं गाँव में दोना पत्तल बनाता हूँ",
    send: "भेजें",
    thinking: "देख रहे हैं...",
    restart: "फिर से शुरू करें",
    examplesLabel: "या इनमें से कोई चुनें",
    examples: [
      "मैं गाँव में दोना पत्तल बनाता हूँ",
      "मैं सिलाई का काम शुरू करना चाहती हूँ",
      "मेरी उम्र 28 है और मैं शहर में रहता हूँ",
    ],
    whatYouGet: "क्या मिलेगा",
    whyYouMayQualify: "आप क्यों पात्र हो सकते हैं",
    documents: "कौन से कागज़ ले जाएँ",
    nextStep: "अब क्या करें",
    source: "स्रोत",
    verifiedOn: "जाँच की तारीख",
    page: "पृष्ठ",
    error: "अभी जवाब नहीं मिल पाया। कृपया दोबारा कोशिश करें।",
  },
  en: {
    title: "Sahayak Setu",
    tagline: "Tell us about your work. We will tell you which government schemes may be for you.",
    placeholder: "For example: I make leaf plates in my village",
    send: "Send",
    thinking: "Looking...",
    restart: "Start again",
    examplesLabel: "Or pick one of these",
    examples: [
      "I make leaf plates at home in my village",
      "I want to start a tailoring business",
      "I am 28 and I live in the city",
    ],
    whatYouGet: "What you get",
    whyYouMayQualify: "Why you may qualify",
    documents: "Documents to carry",
    nextStep: "What to do next",
    source: "Source",
    verifiedOn: "Checked on",
    page: "Page",
    error: "We could not get an answer. Please try again.",
  },
};

function Card({ card, t }) {
  return (
    <article className="card">
      <h2>{card.name}</h2>

      {card.what_you_get && (
        <div className="field">
          <span className="field-label">{t.whatYouGet}</span>
          <p>{card.what_you_get}</p>
        </div>
      )}

      {card.why_you_may_qualify && (
        <div className="field why">
          <span className="field-label">{t.whyYouMayQualify}</span>
          <p>{card.why_you_may_qualify}</p>
        </div>
      )}

      {card.documents?.length > 0 && (
        <div className="field">
          <span className="field-label">{t.documents}</span>
          <ul>
            {card.documents.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
        </div>
      )}

      {card.next_step && (
        <div className="field">
          <span className="field-label">{t.nextStep}</span>
          <p>{card.next_step}</p>
        </div>
      )}

      {/* Citations are attached by the server from the verified corpus, never
          written by the model. If this block is empty, something is wrong. */}
      {card.sources?.length > 0 && (
        <div className="sources">
          {card.sources.map((s, i) => (
            <div key={i}>
              {t.source}:{" "}
              <a href={s.url} target="_blank" rel="noopener noreferrer">
                {s.title || s.url}
              </a>
            </div>
          ))}
          {card.last_verified && (
            <span className="verified">
              {t.verifiedOn}: {card.last_verified}
              {card.source_pages?.length > 0 &&
                ` · ${t.page} ${card.source_pages.join(", ")}`}
            </span>
          )}
        </div>
      )}
    </article>
  );
}

export default function App() {
  const [language, setLanguage] = useState("hi");
  const [turns, setTurns] = useState([]);
  const [asked, setAsked] = useState([]);
  const [answer, setAnswer] = useState(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [draft, setDraft] = useState("");
  const bottom = useRef(null);

  const t = COPY[language];

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, answer, busy]);

  async function send(text) {
    const message = text.trim();
    if (!message || busy) return;

    const conversation = [...turns, { role: "user", text: message }];
    setTurns(conversation);
    setDraft("");
    setBusy(true);
    setFailed(false);

    try {
      const result = await ask(conversation, asked);
      if (result.type === "question") {
        setTurns([...conversation, { role: "assistant", text: result.question }]);
        setAsked(result.asked || asked);
        if (result.language) setLanguage(result.language);
      } else {
        setAnswer(result);
        if (result.language) setLanguage(result.language);
      }
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  function restart() {
    setTurns([]);
    setAsked([]);
    setAnswer(null);
    setFailed(false);
    setDraft("");
  }

  return (
    <div className="app">
      <header>
        <h1>{t.title}</h1>
        <p className="tagline">{t.tagline}</p>
        <div className="lang-toggle" role="group" aria-label="Language">
          <button onClick={() => setLanguage("hi")} aria-pressed={language === "hi"}>
            हिंदी
          </button>
          <button onClick={() => setLanguage("en")} aria-pressed={language === "en"}>
            English
          </button>
        </div>
      </header>

      <main>
        <div className="turns">
          {turns.map((turn, i) => (
            <div key={i} className={`turn ${turn.role === "user" ? "user" : "bot"}`}>
              {turn.text}
            </div>
          ))}
        </div>

        {busy && <p className="thinking">{t.thinking}</p>}
        {failed && <p className="error">{t.error}</p>}

        {turns.length === 0 && !busy && (
          <div className="examples">
            <p>{t.examplesLabel}</p>
            {t.examples.map((example) => (
              <button key={example} className="example" onClick={() => send(example)}>
                {example}
              </button>
            ))}
          </div>
        )}

        {answer && (
          <section aria-live="polite">
            {answer.summary && <p className="summary">{answer.summary}</p>}

            {/* Shown above the cards, not buried under them. */}
            <p className="disclaimer">{answer.disclaimer}</p>

            {answer.cards?.map((card) => (
              <Card key={card.scheme_id} card={card} t={t} />
            ))}

            {answer.closing && <p className="summary">{answer.closing}</p>}

            <button className="restart" onClick={restart}>
              {t.restart}
            </button>
          </section>
        )}
        <div ref={bottom} />
      </main>

      {!answer && (
        <div className="composer">
          <div className="composer-inner">
            <textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                // isComposing matters here more than in most apps. Typing
                // Devanagari on Android goes through an IME, and Enter while
                // a syllable is still being composed means "accept this
                // character", not "send". Without this guard the message
                // fires mid-word for exactly the users we built this for.
                if (e.key !== "Enter" || e.shiftKey) return;
                if (e.nativeEvent?.isComposing || e.keyCode === 229) return;
                e.preventDefault();
                send(draft);
              }}
              placeholder={t.placeholder}
              aria-label={t.placeholder}
              rows={1}
            />
            <button className="send" onClick={() => send(draft)} disabled={busy || !draft.trim()}>
              {t.send}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
