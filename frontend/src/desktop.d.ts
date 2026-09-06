export {};

declare global {
  interface Window {
    retinaDesktop?: {
      chooseReportFolder: () => Promise<string | null>;
      chooseBatchInputFolder: () => Promise<string | null>;
      chooseBatchOutputFolder: () => Promise<string | null>;
    };
  }
}
