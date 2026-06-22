"use client"

import Link from "next/link"
import type { Position } from "@/lib/types"
import { fmtNum, fmtPct, fmtSigned, fmtUsd, pnlColor } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { SideBadge } from "@/components/status-badge"

export function PositionsTable({ positions, loading }: { positions: Position[]; loading: boolean }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">当前持仓 ({positions.length})</CardTitle>
      </CardHeader>
      <CardContent className="px-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead>交易对</TableHead>
                <TableHead>方向</TableHead>
                <TableHead className="text-right">数量</TableHead>
                <TableHead className="text-right">开仓均价</TableHead>
                <TableHead className="text-right">标记价</TableHead>
                <TableHead className="text-right">杠杆</TableHead>
                <TableHead className="text-right">保证金</TableHead>
                <TableHead className="text-right">强平价</TableHead>
                <TableHead className="text-right">未实现盈亏</TableHead>
                <TableHead>所属策略</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading
                ? [0, 1, 2].map((i) => (
                    <TableRow key={i}>
                      <TableCell colSpan={10}>
                        <div className="h-5 w-full animate-pulse rounded bg-muted" />
                      </TableCell>
                    </TableRow>
                  ))
                : positions.map((p) => (
                    <TableRow key={p.id}>
                      <TableCell className="font-medium">{p.symbol}</TableCell>
                      <TableCell>
                        <SideBadge side={p.side} />
                      </TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{fmtNum(p.size, 4)}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{fmtNum(p.entryPrice, p.entryPrice < 10 ? 3 : 2)}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{fmtNum(p.markPrice, p.markPrice < 10 ? 3 : 2)}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{p.leverage}×</TableCell>
                      <TableCell className="text-right font-mono tabular-nums">{fmtUsd(p.margin, 0)}</TableCell>
                      <TableCell className="text-right font-mono tabular-nums text-muted-foreground">
                        {p.liquidationPrice > 0 ? fmtNum(p.liquidationPrice, p.liquidationPrice < 10 ? 3 : 2) : "—"}
                      </TableCell>
                      <TableCell className={`text-right font-mono tabular-nums ${pnlColor(p.unrealizedPnl)}`}>
                        <div>{fmtSigned(p.unrealizedPnl)}</div>
                        <div className="text-xs">{fmtPct(p.unrealizedPnlPct)}</div>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        <Link href={`/strategy/${p.strategyName}`} className="hover:text-foreground transition-colors">
                          {p.strategyName}
                        </Link>
                      </TableCell>
                    </TableRow>
                  ))}
            </TableBody>
          </Table>
        </div>
      </CardContent>
    </Card>
  )
}
