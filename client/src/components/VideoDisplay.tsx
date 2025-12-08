import React from "react";
import styles from "../App.module.css";

interface Props {
  videoUrl: string | null;
  loading: boolean;
  progress?: number;
  status?: string;
}

export const VideoDisplay: React.FC<Props> = ({
  videoUrl,
  loading,
  progress,
  status
}) => {
  return (
    <div className={styles.section}>
      <h3 className={styles.sectionTitle}>Result</h3>
      <div className={styles.videoContainer}>
        {videoUrl ? (
          <video
            className={styles.video}
            controls
            autoPlay
            loop
            src={videoUrl}
          />
        ) : (
          <div className={styles.placeholder}>
            {loading ? (
              <>
                <span>
                  {status || "Generating..."}{" "}
                  {progress ? `${Math.round(progress)}%` : ""}
                </span>
              </>
            ) : (
              <span>Video will appear here</span>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
