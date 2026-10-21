import { useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Pencil, Check, X } from "lucide-react";
import { API, chName } from "@/api";

export const ChamberNameEdit = ({ t, dev, id, onSaved, size = 17, editable }) => {
  const [edit, setEdit] = useState(false);
  const [val, setVal] = useState("");
  const save = async () => {
    try {
      await axios.put(`${API}/devices/${dev.device_id}/chambers/${id}/name`, { name: val.trim() });
      setEdit(false); onSaved?.(); toast.success(t.saved);
    } catch (e) { toast.error(t.saveFailed); }
  };
  if (!edit) return (
    <span className="flex items-center gap-2" style={{ minWidth: 0 }}>
      <span className="font-head" data-testid={`chamber-${id}-name`} style={{ fontSize: size, fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {chName(t, dev, id)}</span>
      {editable && <button className="sp-btn" onClick={() => { setVal(dev?.chamber_names?.[id] || ""); setEdit(true); }} data-testid={`chamber-${id}-rename`} aria-label={t.rename}
        style={{ width: 26, height: 26, flexShrink: 0 }}><Pencil size={12} /></button>}
    </span>
  );
  return (
    <span className="flex items-center gap-1" style={{ flex: 1, minWidth: 0 }}>
      <input autoFocus className="num-input" maxLength={30} value={val} placeholder={`${t.chamberWord} ${id + 1}`} data-testid={`chamber-${id}-name-input`}
        onChange={(e) => setVal(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setEdit(false); }}
        style={{ fontSize: 14, flex: 1, minWidth: 0, padding: "6px 10px" }} />
      <button className="sp-btn" onClick={save} data-testid={`chamber-${id}-name-save`} aria-label={t.save} style={{ color: "var(--primary)" }}><Check size={14} /></button>
      <button className="sp-btn" onClick={() => setEdit(false)} data-testid={`chamber-${id}-name-cancel`} aria-label="cancel"><X size={14} /></button>
    </span>
  );
};
