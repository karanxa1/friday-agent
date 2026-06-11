"use client";

import * as React from "react";
import { motion } from "framer-motion";

export interface ImageGenerationProps {
  /** Real tool status — drives the reveal instead of a fixed fake timer. */
  status: "running" | "done" | "error";
  children: React.ReactNode;
}

/**
 * Progressive blur-reveal for generated images (Vercel-AI-style). While the
 * image is being created, a frosted-glass mask wipes downward over a shimmer
 * placeholder; the moment the real image arrives (status → done) the mask
 * clears to reveal it. Adapted from the reference component to use
 * framer-motion + this project's tokens and real generation state.
 */
export const ImageGeneration = ({ status, children }: ImageGenerationProps) => {
  const [progress, setProgress] = React.useState(0);
  const [loadingState, setLoadingState] = React.useState<
    "starting" | "generating" | "completed"
  >(status === "done" ? "completed" : "starting");
  // Images can take a while; ease the mask toward ~92% over this window, then
  // snap to 100% when the real result lands.
  const duration = 30000;

  React.useEffect(() => {
    if (status === "done") {
      setLoadingState("completed");
      setProgress(100);
      return;
    }
    if (status === "error") {
      setLoadingState("completed");
      setProgress(100);
      return;
    }
    // running
    const startingTimeout = setTimeout(() => {
      setLoadingState("generating");
      const startTime = Date.now();
      const interval = setInterval(() => {
        const elapsed = Date.now() - startTime;
        // Cap at 92% while still running — completion is gated on the result.
        const pct = Math.min(92, (elapsed / duration) * 100);
        setProgress(pct);
      }, 16);
      return () => clearInterval(interval);
    }, 1500);
    return () => clearTimeout(startingTimeout);
  }, [status, duration]);

  const completed = loadingState === "completed";

  return (
    <div className="flex flex-col gap-2">
      <motion.span
        className="bg-[linear-gradient(110deg,#6e6e6e,35%,#f0f0f0,50%,#6e6e6e,75%,#6e6e6e)] bg-[length:200%_100%] bg-clip-text text-[13px] font-medium text-transparent"
        initial={{ backgroundPosition: "200% 0" }}
        animate={{ backgroundPosition: completed ? "0% 0" : "-200% 0" }}
        transition={{
          repeat: completed ? 0 : Infinity,
          duration: 3,
          ease: "linear",
        }}
      >
        {loadingState === "starting" && "Getting started…"}
        {loadingState === "generating" && "Creating image. May take a moment…"}
        {loadingState === "completed" &&
          (status === "error" ? "Generation failed." : "Image created.")}
      </motion.span>

      <div className="relative max-w-md overflow-hidden rounded-xl border border-edge-subtle bg-panel-elevated">
        {children}
        <motion.div
          className="pointer-events-none absolute -top-[25%] h-[125%] w-full backdrop-blur-3xl"
          initial={false}
          animate={{
            clipPath: `polygon(0 ${progress}%, 100% ${progress}%, 100% 100%, 0 100%)`,
            opacity: completed ? 0 : 1,
          }}
          transition={{ ease: "linear", duration: 0.1 }}
          style={{
            clipPath: `polygon(0 ${progress}%, 100% ${progress}%, 100% 100%, 0 100%)`,
            maskImage:
              progress === 0
                ? "linear-gradient(to bottom, black -5%, black 100%)"
                : `linear-gradient(to bottom, transparent ${progress - 5}%, transparent ${progress}%, black ${progress + 5}%)`,
            WebkitMaskImage:
              progress === 0
                ? "linear-gradient(to bottom, black -5%, black 100%)"
                : `linear-gradient(to bottom, transparent ${progress - 5}%, transparent ${progress}%, black ${progress + 5}%)`,
          }}
        />
      </div>
    </div>
  );
};

ImageGeneration.displayName = "ImageGeneration";
