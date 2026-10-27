import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Unlock from "../components/Unlock";
import { useWallet } from "../lib/store";
import { listJournal, addJournal, type JournalEntry } from "../lib/db";
import type { V4Transfer } from "../lib/types";

export default function History() {
  const { status, client } = useWallet();
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const journal = useQuery({
    queryKey: ["journal"],
    enabled: status === "unlocked",
    queryFn: async () => (await listJournal()).sort((a, b) => b.createdAt - a.createdAt),
  });

  const height = useQuery({
    queryKey: ["height"],
    enabled: status === "unlocked" && !!client,
    refetchInterval: 5_000,
    queryFn: async () => JSON.parse(await client!.height()) as { height: number },
  });

  const transfers = useQuery({
    queryKey: ["history-transfers", journal.data?.map((entry) => entry.transfer).join(",")],
    enabled: status === "unlocked" && !!client && !!journal.data,
    queryFn: async () => {
      const out: Record<string, V4Transfer> = {};
      for (const entry of journal.data ?? []) {
        if (!entry.transfer) continue;
        try {
          out[entry.transfer] = JSON.parse(
            await client!.v4_transfer_info(entry.transfer),
          ) as V4Transfer;
        } catch {
          // A transfer that a different chain no longer knows is shown from the journal.
        }
      }
      return out;
    },
  });

  if (status !== "unlocked") return <Unlock />;

  const refund = async (entry: JournalEntry) => {
    if (!entry.transfer) return;
    setBusy(entry.id);
    setError(null);
    try {
      await client!.v4_refund_transfer(entry.transfer);
      await addJournal({
        ...entry,
        id: `refund-${entry.transfer}`,
        kind: "refund",
        summary: `refunded ${entry.amount ?? ""} ${entry.asset ?? ""}`,
        status: "confirmed",
        createdAt: Date.now(),
      });
      await queryClient.invalidateQueries({ queryKey: ["history-transfers"] });
      await queryClient.invalidateQueries({ queryKey: ["journal"] });
      await queryClient.invalidateQueries({ queryKey: ["v4-balances"] });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="panel">
      <h2>History</h2>
      <p className="muted">
        Local journal of sends and claims, reconciled against the on-chain transfer record.
        An open transfer can be refunded after its expiry height.
      </p>

      {error && <p className="error">{error}</p>}

      <table className="table">
        <thead>
          <tr>
            <th>When</th>
            <th>Kind</th>
            <th>Detail</th>
            <th>Status</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(journal.data ?? []).map((entry) => {
            const chain = entry.transfer ? transfers.data?.[entry.transfer] : undefined;
            const expired =
              chain && height.data ? height.data.height >= chain.expiry : false;
            return (
              <tr key={entry.id}>
                <td className="muted small">
                  {new Date(entry.createdAt).toLocaleString()}
                </td>
                <td>{entry.kind}</td>
                <td className="mono small">{entry.summary}</td>
                <td>{chain?.status ?? entry.status ?? "—"}</td>
                <td>
                  {chain?.status === "open" && expired && (
                    <button
                      className="ghost"
                      disabled={busy === entry.id}
                      onClick={() => refund(entry)}
                    >
                      {busy === entry.id ? "Refunding…" : "Refund"}
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
          {journal.data?.length === 0 && (
            <tr>
              <td colSpan={5} className="muted">
                No activity yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  );
}
