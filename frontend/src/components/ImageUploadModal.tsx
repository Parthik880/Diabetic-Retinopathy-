import { useState, useRef, ChangeEvent } from 'react';

interface ImageUploadModalProps {
  eye: 'OS' | 'OD';
  onClose: () => void;
  onImageSelected: (eye: 'OS' | 'OD', imageUrl: string) => void;
}

export function ImageUploadModal({
  eye,
  onClose,
  onImageSelected,
}: ImageUploadModalProps) {
  const [activeMode, setActiveMode] = useState<'upload' | 'camera' | 'samples'>('upload');
  const [cameraActive, setCameraActive] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  const sampleImages = [
    {
      title: 'Bundled sample A (unverified)',
      url: '/samples/retina-a.jpg',
      grade: 'No model result yet'
    },
    {
      title: 'Bundled sample B (unverified)',
      url: '/samples/retina-b.jpg',
      grade: 'No model result yet'
    }
  ];

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = () => {
        setPreviewUrl(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const startCamera = async () => {
    try {
      setCameraActive(true);
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
      }
    } catch {
      alert('Camera access could not be initialized. Please use file upload or preset scans.');
      setCameraActive(false);
    }
  };

  const captureFromVideo = () => {
    if (videoRef.current) {
      const canvas = document.createElement('canvas');
      canvas.width = videoRef.current.videoWidth || 640;
      canvas.height = videoRef.current.videoHeight || 480;
      const ctx = canvas.getContext('2d');
      if (ctx) {
        ctx.drawImage(videoRef.current, 0, 0, canvas.width, canvas.height);
        setPreviewUrl(canvas.toDataURL('image/jpeg'));
        // Stop stream
        const stream = videoRef.current.srcObject as MediaStream;
        stream?.getTracks().forEach((track) => track.stop());
        setCameraActive(false);
      }
    }
  };

  const handleConfirm = () => {
    if (previewUrl) {
      onImageSelected(eye, previewUrl);
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-surface-container-lowest rounded-2xl max-w-lg w-full border-2 border-outline shadow-2xl overflow-hidden animate-scale-up">
        {/* Header */}
        <div className="p-5 bg-surface-container-low border-b-2 border-outline-variant flex justify-between items-center">
          <div className="flex items-center gap-2.5">
            <span className="material-symbols-outlined text-primary text-2xl">add_a_photo</span>
            <div>
              <h3 className="font-headline-md text-lg font-bold text-on-surface">
                Capture / Import Retinal Scan ({eye === 'OS' ? 'Left Eye' : 'Right Eye'})
              </h3>
              <p className="text-xs text-on-surface-variant">
                Select from clinical repository, upload digital fundus file, or capture
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-full hover:bg-surface-container transition-colors text-on-surface-variant"
          >
            <span className="material-symbols-outlined text-xl">close</span>
          </button>
        </div>

        {/* Mode Selector Tabs */}
        <div className="flex border-b border-outline-variant bg-surface-container-low px-4 pt-2 gap-2">
          <button
            onClick={() => setActiveMode('upload')}
            className={`px-3 py-2 text-xs font-bold rounded-t-lg transition-colors ${
              activeMode === 'samples'
                ? 'bg-surface-container-lowest border-t border-x border-outline-variant text-primary'
                : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            Clinical Presets
          </button>
          <button
            onClick={() => setActiveMode('upload')}
            className={`px-3 py-2 text-xs font-bold rounded-t-lg transition-colors ${
              activeMode === 'upload'
                ? 'bg-surface-container-lowest border-t border-x border-outline-variant text-primary'
                : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            Upload File
          </button>
          <button
            onClick={() => {
              setActiveMode('camera');
              startCamera();
            }}
            className={`px-3 py-2 text-xs font-bold rounded-t-lg transition-colors ${
              activeMode === 'camera'
                ? 'bg-surface-container-lowest border-t border-x border-outline-variant text-primary'
                : 'text-on-surface-variant hover:text-on-surface'
            }`}
          >
            Fundus Camera / Webcam
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6">
          {activeMode === 'samples' && (
            <div className="space-y-3">
              <span className="text-xs font-bold text-on-surface block">
                Choose a validated clinical case scan:
              </span>
              <div className="grid grid-cols-2 gap-3">
                {sampleImages.map((s, idx) => (
                  <div
                    key={idx}
                    onClick={() => setPreviewUrl(s.url)}
                    className={`p-2 rounded-lg border cursor-pointer transition-all ${
                      previewUrl === s.url
                        ? 'border-2 border-primary bg-primary/5 ring-2 ring-primary/20'
                        : 'border-outline-variant hover:border-primary'
                    }`}
                  >
                    <div className="w-full aspect-square bg-black rounded overflow-hidden mb-2">
                      <img src={s.url} alt={s.title} className="w-full h-full object-cover" crossOrigin="anonymous" />
                    </div>
                    <span className="text-[11px] font-bold text-on-surface line-clamp-1 block">{s.title}</span>
                    <span className="text-[10px] text-primary font-bold">{s.grade}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeMode === 'upload' && (
            <div className="space-y-4">
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handleFileChange}
                className="hidden"
              />
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-outline hover:border-primary rounded-xl p-8 flex flex-col items-center justify-center gap-3 cursor-pointer bg-surface-container-low hover:bg-surface-container transition-colors"
              >
                <span className="material-symbols-outlined text-4xl text-primary">upload_file</span>
                <span className="text-xs font-bold text-on-surface">Click to Browse or Drag Fundus Photo</span>
                <span className="text-[11px] text-on-surface-variant">Supports DICOM, JPEG, PNG, TIFF</span>
              </div>
            </div>
          )}

          {activeMode === 'camera' && (
            <div className="space-y-4">
              <div className="relative w-full aspect-video bg-black rounded-lg overflow-hidden flex items-center justify-center">
                <video ref={videoRef} className="w-full h-full object-cover" playsInline muted />
              </div>
              {cameraActive && (
                <button
                  type="button"
                  onClick={captureFromVideo}
                  className="w-full py-2.5 bg-primary text-on-primary rounded-lg font-bold text-xs flex items-center justify-center gap-2"
                >
                  <span className="material-symbols-outlined text-base">photo_camera</span>
                  Freeze & Acquire Frame
                </button>
              )}
            </div>
          )}

          {/* Preview confirmation */}
          {previewUrl && (
            <div className="mt-4 pt-4 border-t border-outline-variant flex items-center justify-between">
              <span className="text-xs text-primary font-bold flex items-center gap-1">
                <span className="material-symbols-outlined text-sm">check_circle</span>
                Scan Ready for Analysis
              </span>
              <button
                type="button"
                onClick={handleConfirm}
                className="px-5 py-2 bg-primary text-on-primary rounded-lg font-bold text-xs hover:bg-primary-fixed hover:text-on-primary-fixed transition-colors shadow-xs"
              >
                Apply Scan
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
