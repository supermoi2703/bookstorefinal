from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConfig:
    item_count: int
    action_count: int
    embedding_dim: int = 48
    hidden_dim: int = 96
    sequence_length: int = 10


def build_model(architecture, config):
    import torch
    import torch.nn as nn

    class NextItemModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.item_embedding = nn.Embedding(config.item_count + 1, config.embedding_dim)
            self.action_embedding = nn.Embedding(
                config.action_count + 1, config.embedding_dim // 2
            )
            input_dim = config.embedding_dim + config.embedding_dim // 2 + 1
            if architecture == "SimpleRNN":
                self.encoder = nn.RNN(input_dim, config.hidden_dim, batch_first=True)
                output_dim = config.hidden_dim
            elif architecture == "BiLSTM":
                self.encoder = nn.LSTM(
                    input_dim,
                    config.hidden_dim,
                    batch_first=True,
                    bidirectional=True,
                )
                output_dim = config.hidden_dim * 2
            else:
                self.encoder = nn.LSTM(
                    input_dim, config.hidden_dim, batch_first=True
                )
                output_dim = config.hidden_dim
            self.dropout = nn.Dropout(0.2)
            self.item_head = nn.Linear(output_dim, config.item_count)
            self.action_head = nn.Linear(output_dim, config.action_count)

        def forward(self, items, actions, time_deltas):
            embedded = torch.cat(
                [
                    self.item_embedding(items),
                    self.action_embedding(actions),
                    time_deltas.unsqueeze(-1),
                ],
                dim=-1,
            )
            encoded, _ = self.encoder(embedded)
            final = self.dropout(encoded[:, -1, :])
            return self.item_head(final), self.action_head(final)

    return NextItemModel()
