const FOCUS_RING =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#65f7b0]";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  loading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center p-4">
      <button
        type="button"
        aria-label="Fechar diálogo"
        className="absolute inset-0 bg-slate-950/70 backdrop-blur-sm"
        onClick={loading ? undefined : onCancel}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-description"
        className="relative w-full max-w-md rounded-3xl border border-white/10 bg-slate-950 p-6 shadow-2xl shadow-black/50"
      >
        <h2 id="confirm-dialog-title" className="text-xl font-black text-white">
          {title}
        </h2>
        <p id="confirm-dialog-description" className="mt-3 text-sm leading-6 text-slate-300">
          {description}
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={loading}
            className={`rounded-2xl border border-white/10 px-4 py-2 text-sm font-bold text-slate-200 transition hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={loading}
            className={`rounded-2xl border border-rose-300/30 bg-rose-400/15 px-4 py-2 text-sm font-bold text-rose-100 transition hover:bg-rose-400/25 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`}
          >
            {loading ? "Excluindo..." : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
