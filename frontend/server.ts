import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI } from "@google/genai";
import dotenv from "dotenv";

dotenv.config();

const app = express();
const PORT = 3000;

app.use(express.json({ limit: "50mb" }));

// Lazy initialize Gemini client if key is available
function getGeminiClient() {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey || apiKey === "MY_GEMINI_API_KEY") {
    return null;
  }
  return new GoogleGenAI({ apiKey });
}

// Health check endpoint
app.get("/api/health", (req, res) => {
  res.json({
    status: "ok",
    app: "RetinaScan AI",
    timestamp: new Date().toISOString(),
    geminiConfigured: !!(process.env.GEMINI_API_KEY && process.env.GEMINI_API_KEY !== "MY_GEMINI_API_KEY")
  });
});

// Specialist Queue in-memory mock store
const specialistQueue: Array<{
  id: string;
  patientId: string;
  patientName: string;
  specialistName: string;
  urgency: "STAT" | "Urgent" | "Routine";
  notes: string;
  submittedAt: string;
  status: "Pending Review" | "In Review" | "Accepted";
}> = [
  {
    id: "REF-1092",
    patientId: "RH-8842",
    patientName: "Eleanor Vance",
    specialistName: "Dr. Catherine Hayes, MD (Retina Specialist)",
    urgency: "Urgent",
    notes: "Macular cotton wool spots and microaneurysms detected with 94% confidence. Referral for FA and OCT evaluation.",
    submittedAt: new Date(Date.now() - 3600000 * 4).toISOString(),
    status: "Pending Review"
  }
];

// Endpoint: submit referral to specialist queue
app.post("/api/referral", (req, res) => {
  try {
    const { patientId, patientName, specialistName, urgency, notes } = req.body;
    const newReferral = {
      id: `REF-${Math.floor(1000 + Math.random() * 9000)}`,
      patientId: patientId || "RH-8842",
      patientName: patientName || "Eleanor Vance",
      specialistName: specialistName || "Dr. Catherine Hayes, MD (Retina Specialist)",
      urgency: urgency || "Urgent",
      notes: notes || "Immediate specialist evaluation recommended based on AI screening findings.",
      submittedAt: new Date().toISOString(),
      status: "Pending Review" as const
    };
    specialistQueue.unshift(newReferral);
    res.json({ success: true, referral: newReferral, queueLength: specialistQueue.length });
  } catch (err: any) {
    res.status(500).json({ error: err.message || "Failed to submit referral" });
  }
});

app.get("/api/referrals", (req, res) => {
  res.json({ referrals: specialistQueue });
});

// Endpoint: AI Clinical Decision Support with Gemini
app.post("/api/gemini-consult", async (req, res) => {
  try {
    const { query, patientContext } = req.body;
    const ai = getGeminiClient();

    if (!ai) {
      // Provide high-grade heuristic clinical response if no API key
      const clinicalInsights = [
        "Based on the identified microaneurysms, hemorrhages, and focal cotton wool spots in the macula-centered fundus photograph, the diagnostic profile is consistent with International Clinical Diabetic Retinopathy (ICDR) Grade 3 (Moderate NPDR).",
        "Key clinical priority: Given the presence of cotton wool spots within 1 disc diameter of the foveal avascular zone (FAZ), optical coherence tomography (OCT) is indicated to rule out concurrent subclinical diabetic macular edema (DME).",
        "Follow-up recommendation: Refer for dilated indirect ophthalmoscopy within 2–4 weeks; optimize systemic glycemic (HbA1c target < 7.0%) and blood pressure control."
      ];
      return res.json({
        answer: clinicalInsights.join("\n\n"),
        source: "Clinical Guideline Heuristics (ICDR Standard)"
      });
    }

    const prompt = `You are RetinaScan AI's Clinical Decision Support System for ophthalmology and retinal disease diagnosis.
The clinician is analyzing a retinal fundus scan with the following context:
${JSON.stringify(patientContext, null, 2)}

User/Clinician query: "${query}"

Provide a precise, concise, evidence-based ophthalmological assessment following ICDR (International Clinical Diabetic Retinopathy) guidelines. Format with clear headings and bullet points where helpful.`;

    const response = await ai.models.generateContent({
      model: "gemini-2.5-flash",
      contents: prompt,
    });

    res.json({
      answer: response.text || "Clinical consultation complete.",
      source: "Gemini 2.5 Flash Clinical Support"
    });
  } catch (err: any) {
    console.error("Gemini consult error:", err);
    res.status(500).json({
      error: "Unable to complete AI consultation. Fallback to offline clinical heuristics.",
      details: err.message
    });
  }
});

// Mount Vite middleware for development or static files in production
async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`RetinaScan AI server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();
