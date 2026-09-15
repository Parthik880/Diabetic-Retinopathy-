export {};

declare global {
  interface Window {
    retinaDesktop?: {
      contactPatient: (action: { kind: 'email' | 'sms' | 'call'; address: string; subject?: string; body?: string }) => Promise<{ opened: boolean }>;
      openDataFolder: () => Promise<{ opened: boolean }>;
      chooseReportFolder: () => Promise<string | null>;
      chooseBatchInputFolder: () => Promise<string | null>;
      chooseBatchOutputFolder: () => Promise<string | null>;
    };
  }
}
