# ADR 0002: 核心邏輯不綁定單一 Provider

## Context

若 Memory Manager 直接依賴特定 LLM 或 embedding SDK，測試需要網路與 API 成本，替換模型也會影響 domain code。

## Decision

核心 policy 只依賴小型 `Protocol`。真實 provider、deterministic fake、token counter 與 vector backend 都由 adapter 實作。

## Consequences

- 核心測試可以離線且 deterministic。
- Provider 成本、延遲與錯誤可以分開量測。
- 每個 adapter 必須負責錯誤映射、重試與版本識別。

