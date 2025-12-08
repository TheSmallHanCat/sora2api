import { useState, useEffect, useRef } from "react";
import { getAccounts, getModels, streamChatCompletion } from "./api/client";
import type { Account, Model } from "./api/types";
import { AccountSelector } from "./components/AccountSelector";
import { AccountInfo } from "./components/AccountInfo";
import { ModelSelector } from "./components/ModelSelector";
import { PromptInput } from "./components/PromptInput";
import { VideoDisplay } from "./components/VideoDisplay";
import { ApiKeyInput } from "./components/ApiKeyInput";
import styles from "./App.module.css";

function App() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [models, setModels] = useState<Model[]>([]);

  // Initialize state from localStorage
  const [selectedEmail, setSelectedEmail] = useState<string>(
    () => localStorage.getItem("sora_selected_email") || ""
  );
  const [selectedModel, setSelectedModel] = useState<string>(
    () => localStorage.getItem("sora_selected_model") || ""
  );
  const [prompt, setPrompt] = useState<string>(
    () => localStorage.getItem("sora_prompt") || ""
  );

  const [loading, setLoading] = useState<boolean>(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [progress, setProgress] = useState<number>(0);
  const [status, setStatus] = useState<string>("");
  const [logs, setLogs] = useState<string[]>([]);
  const logsEndRef = useRef<HTMLDivElement>(null);

  // Persist state to localStorage
  useEffect(() => {
    localStorage.setItem("sora_selected_email", selectedEmail);
  }, [selectedEmail]);

  useEffect(() => {
    localStorage.setItem("sora_selected_model", selectedModel);
  }, [selectedModel]);

  useEffect(() => {
    localStorage.setItem("sora_prompt", prompt);
  }, [prompt]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [accountsData, modelsData] = await Promise.all([
          getAccounts(),
          getModels()
        ]);
        setAccounts(accountsData);
        setModels(modelsData);

        // Set default email if none selected
        if (accountsData.length > 0) {
          setSelectedEmail((prev) => prev || accountsData[0].email);
        }

        // Set default model if none selected
        if (modelsData.length > 0) {
          setSelectedModel((prev) => {
            if (prev) return prev;
            // Prefer video models
            const videoModel = modelsData.find((m) => m.id.includes("video"));
            return videoModel ? videoModel.id : modelsData[0].id;
          });
        }
      } catch (error) {
        console.error("Failed to fetch initial data:", error);
      }
    };
    fetchData();
  }, []);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  const selectedAccount =
    accounts.find((a) => a.email === selectedEmail) || null;

  const handleGenerate = async () => {
    if (!selectedModel || !prompt) return;

    setLoading(true);
    setVideoUrl(null);
    setProgress(0);
    setStatus("Initializing...");
    setLogs([]);

    try {
      await streamChatCompletion(
        {
          model: selectedModel,
          messages: [{ role: "user", content: prompt }],
          email: selectedEmail
        },
        (chunk) => {
          const delta = chunk.choices[0]?.delta;

          // Handle reasoning content (logs/status)
          if (delta?.reasoning_content) {
            const content = delta.reasoning_content;
            setLogs((prev) => [...prev, content]);

            // Try to extract progress percentage
            const progressMatch = content.match(/(\d+)%/);
            if (progressMatch) {
              setProgress(parseInt(progressMatch[1]));
            }

            // Update status based on content
            if (content.includes("Generation Process Begins"))
              setStatus("Generating...");
            if (content.includes("Uploading image")) setStatus("Uploading...");
            if (content.includes("Caching")) setStatus("Caching...");
          }

          // Handle final content (video URL)
          if (delta?.content) {
            const content = delta.content;
            // Extract src from video tag: <video src='...' ...>
            const srcMatch = content.match(/src=['"]([^'"]+)['"]/);
            if (srcMatch) {
              setVideoUrl(srcMatch[1]);
            }
          }
        },
        (error) => {
          console.error("Generation error:", error);
          setStatus("Error: " + error.message);
          setLoading(false);
        },
        () => {
          setLoading(false);
          setStatus("Completed");
        }
      );
    } catch (error) {
      console.error("Request failed:", error);
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1 className={styles.title}>Sora2API Client</h1>
      </header>

      <main className={styles.main}>
        <aside className={styles.sidebar}>
          <ApiKeyInput />
          <AccountSelector
            accounts={accounts}
            selectedEmail={selectedEmail}
            onSelect={setSelectedEmail}
          />
          <AccountInfo account={selectedAccount} />
          <ModelSelector
            models={models}
            selectedModel={selectedModel}
            onSelect={setSelectedModel}
          />
        </aside>

        <div className={styles.content}>
          <PromptInput
            prompt={prompt}
            onChange={setPrompt}
            onSubmit={handleGenerate}
            loading={loading}
          />

          <VideoDisplay
            videoUrl={videoUrl}
            loading={loading}
            progress={progress}
            status={status}
          />

          {logs.length > 0 && (
            <div className={styles.section}>
              <h3 className={styles.sectionTitle}>Logs</h3>
              <div
                style={{
                  maxHeight: "200px",
                  overflowY: "auto",
                  fontFamily: "monospace",
                  fontSize: "0.875rem",
                  whiteSpace: "pre-wrap",
                  color: "var(--text-secondary)"
                }}
              >
                {logs.map((log, i) => (
                  <div key={i}>{log}</div>
                ))}
                <div ref={logsEndRef} />
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;
