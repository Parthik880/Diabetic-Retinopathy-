export {};

declare global {
  interface Window {
    retinaDesktop?: {
      chooseReportFolder: () => Promise<string | null>;
      openDataFolder: () => Promise<{ opened: boolean; error?: string }>;
      copyText: (text: string) => Promise<{ copied: boolean }>;
      openCommunication: (request:
        | { action: 'email'; recipient: string; subject: string; body: string }
        | { action: 'call'; recipient: string }
      ) => Promise<{ opened: boolean; error?: string }>;
    };
  }
}
