"use client"

import type { AssetBalance } from "@/lib/types"
import { fmtNum, fmtUsd } from "@/lib/format"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

export function AssetsTable({ assets, loading }: { assets: AssetBalance[]; loading: boolean }) {
  return (
    <Card className="h-full">
      <CardHeader>
        <CardTitle className="text-sm font-medium">资产明细</CardTitle>
      </CardHeader>
      <CardContent className="px-0">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              <TableHead>币种</TableHead>
              <TableHead className="text-right">总额</TableHead>
              <TableHead className="text-right">可用</TableHead>
              <TableHead className="text-right">冻结</TableHead>
              <TableHead className="text-right">估值</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading
              ? [0, 1, 2, 3].map((i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={5}>
                      <div className="h-5 w-full animate-pulse rounded bg-muted" />
                    </TableCell>
                  </TableRow>
                ))
              : assets.map((a) => (
                  <TableRow key={a.asset}>
                    <TableCell className="font-medium">{a.asset}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{fmtNum(a.total, 4)}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums text-muted-foreground">{fmtNum(a.available, 4)}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums text-muted-foreground">{fmtNum(a.inOrder, 4)}</TableCell>
                    <TableCell className="text-right font-mono tabular-nums">{fmtUsd(a.valueUsdt)}</TableCell>
                  </TableRow>
                ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}
