export {};

declare global {
  interface Window {
    retinaDesktop?: {
      chooseReportFolder: () => Promise<string | null>;
    };
  }
}
