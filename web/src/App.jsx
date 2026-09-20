import { useEffect, useRef, useState } from "react";
import { ask, transcribe } from "./api";
import { micSupported, startRecording } from "./mic";

const COPY = {
  hi: {
    title: "सहायक सेतु",
    tagline: "अपना काम बताइए। हम बताएँगे कौन सी सरकारी योजना आपके लिए हो सकती है।",
    namePrompt: "आपका नाम क्या है?",
    namePlaceholder: "जैसे: सीता",
    nameNote: "नाम सिर्फ़ आपके फ़ोन पर रहता है। हम इसे कहीं नहीं भेजते।",
    start: "आगे बढ़ें",
    greeting: (name) => `नमस्ते ${name}। अपना काम बताइए।`,
    placeholder: "जैसे: मैं गाँव में दोना पत्तल बनाता हूँ",
    send: "भेजें",
    thinking: "देख रहे हैं...",
    restart: "फिर से शुरू करें",
    examplesLabel: "या इनमें से कोई चुनें",
    examples: [
      "मैं गाँव में दोना पत्तल बनाता हूँ",
      "मैं सिलाई का काम शुरू करना चाहती हूँ",
      "मैं खेती के साथ छोटा काम शुरू करना चाहता हूँ",
    ],
    choose: "चुनिए",
    skip: "पता नहीं",
    whatYouGet: "क्या मिलेगा",
    rates: "आपके लिए लागू दरें",
    ratesPossible: "ये भी लागू हो सकती हैं",
    whyYouMayQualify: "आप क्यों पात्र हो सकते हैं",
    documents: "कौन से कागज़ ले जाएँ",
    stillToConfirm: "कार्यालय में यह पूछें",
    nextStep: "अब क्या करें",
    source: "स्रोत",
    verifiedOn: "जाँच की तारीख",
    page: "पृष्ठ",
    error: "अभी जवाब नहीं मिल पाया। कृपया दोबारा कोशिश करें।",
    speak: "बोलिए",
    listening: "सुन रहे हैं... छोड़ने पर रुक जाएगा",
    speakHint: "बोलकर बताइए, या टाइप कीजिए",
    speechFailed: "आवाज़ समझ नहीं आई। कृपया टाइप कीजिए।",
    notEligible: "यह योजना अभी आप पर लागू नहीं होती",
  },
  en: {
    title: "Sahayak Setu",
    tagline: "Tell us about your work. We will tell you which government schemes may be for you.",
    namePrompt: "What is your name?",
    namePlaceholder: "For example: Sita",
    nameNote: "Your name stays on your phone. We never send it anywhere.",
    start: "Continue",
    greeting: (name) => `Hello ${name}. Tell us about your work.`,
    placeholder: "For example: I make leaf plates in my village",
    send: "Send",
    thinking: "Looking...",
    restart: "Start again",
    examplesLabel: "Or pick one of these",
    examples: [
      "I make leaf plates at home in my village",
      "I want to start a tailoring business",
      "I farm and want to start a small business too",
    ],
    choose: "Choose one",
    skip: "I do not know",
    whatYouGet: "What you get",
    rates: "Rates that apply to you",
    ratesPossible: "These may also apply",
    whyYouMayQualify: "Why you may qualify",
    documents: "Documents to carry",
    stillToConfirm: "Ask about this at the office",
    nextStep: "What to do next",
    source: "Source",
    verifiedOn: "Checked on",
    page: "Page",
    error: "We could not get an answer. Please try again.",
    speak: "Hold to speak",
    listening: "Listening... let go to stop",
    speakHint: "Speak, or type instead",
    speechFailed: "We could not hear that. Please type instead.",
    notEligible: "This scheme does not apply to you right now",
  },
};

/* applies_when is transcribed verbatim, and for some modifiers that means
   machine syntax like "caste_category in [sc, st] OR gender == female".
   True, but not a sentence to put in front of a person. Prose conditions
   such as "exports 25% to 50% of total sales" are shown as written. */
function readableCondition(condition) {
  if (!condition) return null;
  if (/[[\]]|==|\sOR\s|\sAND\s/.test(condition)) return null;
  return condition;
}

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true" focusable="false">
      <path
        d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z"
        fill="currentColor"
      />
      <path
        d="M19 11a1 1 0 1 0-2 0 5 5 0 0 1-10 0 1 1 0 1 0-2 0 7 7 0 0 0 6 6.93V20H8a1 1 0 1 0 0 2h8a1 1 0 1 0 0-2h-3v-2.07A7 7 0 0 0 19 11Z"
        fill="currentColor"
      />
    </svg>
  );
}

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

      {/* Selected by Python from the profile, copied word for word from the
          source. Shown as separate lines because the document states a base
          rate and separate additions, and no total. */}
      {card.rates?.length > 0 && (
        <div className="field rates">
          <span className="field-label">{t.rates}</span>
          <ul>
            {card.rates.map((r) => (
              <li key={r.modifier_id}>
                {r.rate}
                {r.source_page && <span className="cite"> ({t.page} {r.source_page})</span>}
              </li>
            ))}
          </ul>
        </div>
      )}

      {card.rates_possible?.length > 0 && (
        <div className="field">
          <span className="field-label">{t.ratesPossible}</span>
          <ul>
            {card.rates_possible.map((r) => (
              <li key={r.modifier_id}>
                {r.rate}
                {readableCondition(r.condition) && (
                  <span className="cite"> - {readableCondition(r.condition)}</span>
                )}
              </li>
            ))}
          </ul>
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
            {card.documents.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        </div>
      )}

      {card.still_to_confirm?.length > 0 && (
        <div className="field confirm">
          <span className="field-label">{t.stillToConfirm}</span>
          <ul>
            {card.still_to_confirm.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        </div>
      )}

      {card.next_step && (
        <div className="field">
          <span className="field-label">{t.nextStep}</span>
          <p>{card.next_step}</p>
        </div>
      )}

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
              {card.source_pages?.length > 0 && ` · ${t.page} ${card.source_pages.join(", ")}`}
            </span>
          )}
        </div>
      )}
    </article>
  );
}

/* The answer control for one question. Tapping beats typing on a cheap phone
   in a second script: a tap cannot be misspelled and needs no keyboard. */
function Answer({ question, t, onAnswer, disabled }) {
  const [selected, setSelected] = useState("");

  if (question.input_type === "select") {
    return (
      <div className="answer">
        <span className="field-label">{t.choose}</span>
        <select
          className="select"
          value={selected}
          disabled={disabled}
          onChange={(e) => {
            const option = question.options.find((o) => String(o.value) === e.target.value);
            setSelected(e.target.value);
            if (option) onAnswer(option.value, option.label);
          }}
        >
          <option value="">{t.choose}</option>
          {question.options.map((o) => (
            <option key={String(o.value)} value={String(o.value)}>{o.label}</option>
          ))}
        </select>
      </div>
    );
  }

  if (question.options?.length > 0) {
    return (
      <div className="answer">
        <span className="field-label">{t.choose}</span>
        {question.options.map((o) => (
          <button
            key={String(o.label)}
            className="option"
            disabled={disabled}
            onClick={() => onAnswer(o.value, o.label)}
          >
            {o.label}
          </button>
        ))}
        <button className="option skip" disabled={disabled} onClick={() => onAnswer(null, t.skip)}>
          {t.skip}
        </button>
      </div>
    );
  }

  return null;
}

export default function App() {
  const [language, setLanguage] = useState("hi");
  const [name, setName] = useState("");
  const [nameDraft, setNameDraft] = useState("");
  const [turns, setTurns] = useState([]);
  const [asked, setAsked] = useState([]);
  const [answers, setAnswers] = useState({});
  const [question, setQuestion] = useState(null);
  const [answer, setAnswer] = useState(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [draft, setDraft] = useState("");
  const [recording, setRecording] = useState(false);
  const [speechError, setSpeechError] = useState(false);
  const recorder = useRef(null);
  const bottom = useRef(null);
  const canSpeak = micSupported();

  const t = COPY[language];

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, answer, busy, question]);

  async function submit(conversation, nextAnswers, nextAsked) {
    setBusy(true);
    setFailed(false);
    // A failed recording is about the last attempt, not this one.
    setSpeechError(false);
    setQuestion(null);
    try {
      const result = await ask(conversation, nextAsked, nextAnswers);
      if (result.language) setLanguage(result.language);
      if (result.type === "question") {
        setTurns([...conversation, { role: "assistant", text: result.question }]);
        setAsked(result.asked || nextAsked);
        setQuestion(result);
      } else {
        setTurns(conversation);
        setAnswer(result);
      }
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  function describe(text) {
    const message = text.trim();
    if (!message || busy) return;
    const conversation = [...turns, { role: "user", text: message }];
    setTurns(conversation);
    setDraft("");
    submit(conversation, answers, asked);
  }

  /* value === null means "I do not know": the field stays absent, the matcher
     keeps it UNKNOWN, and the person is told to confirm it at the office. */
  function answerQuestion(value, label) {
    if (busy || !question) return;
    const conversation = [...turns, { role: "user", text: label }];
    const nextAnswers = value === null ? answers : { ...answers, [question.field]: value };
    setTurns(conversation);
    setAnswers(nextAnswers);
    submit(conversation, nextAnswers, asked);
  }

  async function beginSpeaking() {
    if (busy || recording) return;
    setSpeechError(false);
    try {
      recorder.current = await startRecording();
      setRecording(true);
    } catch {
      // Permission refused, or no microphone. The keyboard is still there.
      setSpeechError(true);
    }
  }

  async function finishSpeaking() {
    if (!recording || !recorder.current) return;
    setRecording(false);
    setBusy(true);
    try {
      const clip = await recorder.current.stop();
      recorder.current = null;
      const result = await transcribe(clip.audio, clip.contentType);
      if (result.text) {
        // Put it in the box rather than sending it. A person should see what
        // was heard, and be able to correct it, before it becomes an answer.
        setDraft(result.text);
        if (result.language) setLanguage(result.language);
      } else {
        setSpeechError(true);
      }
    } catch {
      setSpeechError(true);
    } finally {
      setBusy(false);
    }
  }

  function restart() {
    setSpeechError(false);
    setTurns([]);
    setAsked([]);
    setAnswers({});
    setQuestion(null);
    setAnswer(null);
    setFailed(false);
    setDraft("");
  }

  const header = (
    <header>
      <h1>{t.title}</h1>
      <p className="tagline">{t.tagline}</p>
      <div className="lang-toggle" role="group" aria-label="Language">
        <button onClick={() => setLanguage("hi")} aria-pressed={language === "hi"}>हिंदी</button>
        <button onClick={() => setLanguage("en")} aria-pressed={language === "en"}>English</button>
      </div>
    </header>
  );

  // The name never leaves the device. It is here so the interview feels like
  // a conversation, and it is deliberately not part of any request.
  if (!name) {
    return (
      <div className="app">
        {header}
        <main>
          <div className="name-step">
            <label className="name-label" htmlFor="name">{t.namePrompt}</label>
            <input
              id="name"
              className="name-input"
              value={nameDraft}
              onChange={(e) => setNameDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                if (e.nativeEvent?.isComposing || e.keyCode === 229) return;
                e.preventDefault();
                if (nameDraft.trim()) setName(nameDraft.trim());
              }}
              placeholder={t.namePlaceholder}
              autoComplete="off"
            />
            <p className="name-note">{t.nameNote}</p>
            <button
              className="send wide"
              disabled={!nameDraft.trim()}
              onClick={() => setName(nameDraft.trim())}
            >
              {t.start}
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="app">
      {header}
      <main>
        {turns.length === 0 && <p className="greeting">{t.greeting(name)}</p>}

        <div className="turns">
          {turns.map((turn, i) => (
            <div key={i} className={`turn ${turn.role === "user" ? "user" : "bot"}`}>
              {turn.text}
            </div>
          ))}
        </div>

        {busy && !recording && <p className="thinking">{t.thinking}</p>}
        {recording && <p className="listening">{t.listening}</p>}
        {failed && <p className="error">{t.error}</p>}
        {speechError && <p className="error">{t.speechFailed}</p>}

        {question && !busy && (
          <Answer question={question} t={t} onAnswer={answerQuestion} disabled={busy} />
        )}

        {turns.length === 0 && !busy && (
          <div className="examples">
            <p>{t.examplesLabel}</p>
            {t.examples.map((example) => (
              <button key={example} className="example" onClick={() => describe(example)}>
                {example}
              </button>
            ))}
          </div>
        )}

        {answer && (
          <section aria-live="polite">
            {answer.summary && <p className="summary">{answer.summary}</p>}
            <p className="disclaimer">{answer.disclaimer}</p>

            {answer.not_eligible?.length > 0 && (
              <div className="card">
                <span className="field-label">{t.notEligible}</span>
                {answer.not_eligible.map((n, i) => (
                  <div className="field" key={i}>
                    <p><strong>{n.name}</strong></p>
                    <p>{n.reason}</p>
                    {n.source_pages?.length > 0 && (
                      <span className="cite">{t.page} {n.source_pages.join(", ")}</span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {answer.cards?.map((card) => <Card key={card.scheme_id} card={card} t={t} />)}

            {answer.closing && <p className="summary">{answer.closing}</p>}
            <button className="restart" onClick={restart}>{t.restart}</button>
          </section>
        )}
        <div ref={bottom} />
      </main>

      {/* Typing is only offered for the opening description. Every question
          after that is answered by tapping. */}
      {!answer && !question && (
        <div className="composer">
          <div className="composer-inner">
            <textarea
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                if (speechError) setSpeechError(false);
              }}
              onKeyDown={(e) => {
                if (e.key !== "Enter" || e.shiftKey) return;
                if (e.nativeEvent?.isComposing || e.keyCode === 229) return;
                e.preventDefault();
                describe(draft);
              }}
              placeholder={t.placeholder}
              aria-label={t.placeholder}
              rows={1}
            />
            {canSpeak && !draft.trim() ? (
              <button
                className={`send mic${recording ? " recording" : ""}`}
                aria-label={t.speak}
                onPointerDown={beginSpeaking}
                onPointerUp={finishSpeaking}
                onPointerLeave={finishSpeaking}
                onPointerCancel={finishSpeaking}
                disabled={busy && !recording}
              >
                <MicIcon />
              </button>
            ) : (
              <button className="send" onClick={() => describe(draft)} disabled={busy || !draft.trim()}>
                {t.send}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
