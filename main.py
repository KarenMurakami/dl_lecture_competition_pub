# -*- coding: utf-8 -*-
"""main.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1kF83YurZS7K5Z6QCuIY2MKUKsM28zA8Y
"""

import re
import random
import time
from statistics import mode

from PIL import Image
import numpy as np
import pandas
import torch
import torch.nn as nn
import torchvision
from torchvision import transforms
import pandas as pd
from torch.utils.data import Dataset, DataLoader
from transformers import BertTokenizer, BertModel
from PIL import Image
from collections import Counter
import re
from torch import Tensor
# BERTのトークナイザーを初期化 (大文字小文字を区別しない)
tokenizer = BertTokenizer.from_pretrained('bert-base-uncased')
bert_model = BertModel.from_pretrained('bert-base-uncased')
bert_size = 768

from torch import Tensor
#分散表現のサンプル
sample_text = "I am Karen. I am graduate yudkajeow"
sample_tokens = tokenizer(sample_text, return_tensors='pt')
print(sample_tokens)
sample_embedding = bert_model(**sample_tokens).last_hidden_state.mean(dim=1)
print(sample_embedding, sample_embedding.shape)
#sample_re_tokens = [find_closest_token(e) for e in sample_embedding]
#print(sample_re_tokens)
#result = tokenizer.decode(sample_tokens.input_ids[0], skip_special_tokens=True)
result = tokenizer.decode(Tensor([[ 101, 1045, 2572, 8129, 1012, 1045, 2572, 4619, 9805, 2094, 2912, 6460,
         5004,  102]])[0], skip_special_tokens=True)
print(result)

#from google.colab import drive
#drive.mount('/content/drive')

torch.backends.cudnn.benchmark = True

import os
import shutil
from concurrent.futures import ThreadPoolExecutor
'''src_dir = "/content/drive/MyDrive/Colab Notebooks/DLBasics2023_colab/VQA/data"
dst_dir = '/content/data'
os.makedirs(dst_dir, exist_ok=True)
files_to_copy = []
for root, _, files in os.walk(src_dir):
  for file in files:
    src_file = os.path.join(root, file)
    dst_file = os.path.join(dst_dir, os.path.relpath(src_file, src_dir))
    files_to_copy.append((src_file, dst_file))

def copy_file(src_dst):
  src_file, dst_file = src_dst
  dst_file_dir = os.path.dirname(dst_file)
  os.makedirs(dst_file_dir, exist_ok=True)
  try:
    shutil.copy2(src_file, dst_file)
  except Exception as e:
    print(f"error {src_file} to {dst_file}: {e}")

with ThreadPoolExecutor(max_workers=24) as executor:
  executor.map(copy_file, files_to_copy)

copied_files = [os.path.join(root, file) for root, _, files in os.walk(dst_dir) for file in files]
missing_files = [src for src, dst in files_to_copy if dst not in copied_files]

if missing_files:
  print(f"missing: {missing_files}")
else:
  print("success")'''

def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


def process_text(text):
    # lowercase
    text = text.lower()

    # 数詞を数字に変換
    num_word_to_digit = {
        'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
        'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
        'ten': '10'
    }
    for word, digit in num_word_to_digit.items():
        text = text.replace(word, digit)

    # 小数点のピリオドを削除
    text = re.sub(r'(?<!\d)\.(?!\d)', '', text)

    # 冠詞の削除
    text = re.sub(r'\b(a|an|the)\b', '', text)

    # 短縮形のカンマの追加
    contractions = {
        "dont": "don't", "isnt": "isn't", "arent": "aren't", "wont": "won't",
        "cant": "can't", "wouldnt": "wouldn't", "couldnt": "couldn't"
    }
    for contraction, correct in contractions.items():
        text = text.replace(contraction, correct)

    # 句読点をスペースに変換
    text = re.sub(r"[^\w\s':]", ' ', text)

    # 句読点をスペースに変換
    text = re.sub(r'\s+,', ',', text)

    # 連続するスペースを1つに変換
    text = re.sub(r'\s+', ' ', text).strip()

    return text

# 1. データローダーの作成
class VQADataset(torch.utils.data.Dataset):
    def __init__(self, df_path, image_dir, dict_path = None, transform=None, answer=True):
        self.transform = transform  # 画像の前処理
        self.image_dir = image_dir  # 画像ファイルのディレクトリ
        self.df = pandas.read_json(df_path)  # 画像ファイルのパス，question, answerを持つDataFrame
        self.answer = answer

        # question / answerの辞書を作成
        self.question2idx = {}
        self.answer2idx = {}
        self.idx2question = {}
        self.idx2answer = {}

         # ここにファイル由来の辞書　self.question2idx　self.idx2question
        if dict_path:
          df = pd.read_csv(dict_path)
          print(df.columns)
          # 単語->ID
          self.question2idx = dict(zip(df['answer'], df['class_id']))
          self.answer2idx = dict(zip(df['answer'], df['class_id']))

        # 質問文に含まれる単語を辞書に追加
        for question in self.df["question"]:
            question = process_text(question)
            words = question.split(" ")
            for word in words:
                if word not in self.question2idx:
                    self.question2idx[word] = len(self.question2idx)
        self.idx2question = {v: k for k, v in self.question2idx.items()}  # 逆変換用の辞書(question)

        if self.answer:
            #回答
            for answers in self.df["answers"]:
                for answer in answers:
                    word = answer["answer"]
                    word = process_text(word)
                    if word not in self.answer2idx:
                        self.answer2idx[word] = len(self.answer2idx)
            self.idx2answer = {v: k for k, v in self.answer2idx.items()}  # 逆変換用の辞書(answer)

    def update_dict(self, dataset):
        """
        検証用データ，テストデータの辞書を訓練データの辞書に更新する．

        Parameters
        ----------
        dataset : Dataset
            訓練データのDataset
        """
        self.question2idx = dataset.question2idx
        self.answer2idx = dataset.answer2idx
        self.idx2question = dataset.idx2question
        self.idx2answer = dataset.idx2answer

    def __getitem__(self, idx):
        """
        対応するidxのデータ（画像，質問，回答）を取得．

        Parameters
        ----------
        idx : int
            取得するデータのインデックス

        Returns
        -------
        image : torch.Tensor  (C, H, W)
            画像データ
        question : torch.Tensor  (vocab_size)
            質問文をone-hot表現に変換したもの
        answers : torch.Tensor  (n_answer)
            10人の回答者の回答のid
        mode_answer_idx : torch.Tensor  (1)
            10人の回答者の回答の中で最頻値の回答のid
        """

        '''image = Image.open(f"{self.image_dir}/{self.df['image'][idx]}")
        if self.transform:
            image = self.transform(image)

        # 質問文のトークン化
        question_text = process_text(self.df["question"][idx])
        question_tokens = tokenizer.encode(question_text, add_special_tokens=True)

        if self.answer:
            # 回答のトークン化
            answers = [tokenizer.encode(self.process_text(answer["answer"]), add_special_tokens=True) for answer in self.df["answers"][idx]]
            # 回答の最頻値を取得
            flat_answers = [token for sublist in answers for token in sublist]
            mode_answer_idx = Counter(flat_answers).most_common(1)[0][0]

            return image, torch.tensor(question_tokens), torch.tensor(flat_answers), int(mode_answer_idx)

        else:
            return image, torch.tensor(question_tokens)'''


        image = Image.open(f"{self.image_dir}/{self.df['image'][idx]}")
        if self.transform:
            image = self.transform(image)

        # 分散表現
        question_text = process_text(self.df["question"][idx])
        question_tokens = tokenizer(question_text, return_tensors='pt')
        with torch.no_grad():
            question_embedding = bert_model(**question_tokens).last_hidden_state.mean(dim=1) #(1, 768)

        if self.answer:
            answers = [self.answer2idx[process_text(answer["answer"])] for answer in self.df["answers"][idx]] #(10, len(self.answer2idx))
            mode_answer_idx = mode(answers)  # 最頻値を取得（正解ラベル）(1, len(self.answer2idx))

            return image, question_embedding.squeeze(), torch.Tensor(answers), int(mode_answer_idx)

        else:
            return image, question_embedding.squeeze()
    def __len__(self):
        return len(self.df)

# 2. 評価指標の実装
# 簡単にするならBCEを利用する
def VQA_criterion(batch_pred: torch.Tensor, batch_answers: torch.Tensor):
    total_acc = 0.

    for pred, answers in zip(batch_pred, batch_answers):
        acc = 0.
        for i in range(len(answers)):
            num_match = 0
            for j in range(len(answers)):
                if i == j:
                    continue
                if pred == answers[j]:
                    num_match += 1
            acc += min(num_match / 3, 1)
        total_acc += acc / 10

    return total_acc / len(batch_pred)

# 3. モデルのの実装
# ResNetを利用できるようにしておく
class BasicBlock(nn.Module):
    expansion = 1

    def __init__(self, in_channels: int, out_channels: int, stride: int = 1):
        super().__init__()

        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=3, stride=stride, padding=1)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, stride=1, padding=1)
        self.bn2 = nn.BatchNorm2d(out_channels)
        self.relu = nn.ReLU(inplace=True)

        self.shortcut = nn.Sequential()
        if stride != 1 or in_channels != out_channels:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=stride),
                nn.BatchNorm2d(out_channels)
            )

    def forward(self, x):
        residual = x
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))

        out += self.shortcut(residual)
        out = self.relu(out)

        return out


class BottleneckBlock(nn.Module):
    expansion = 4

    def __init__(self, in_channels: int, out_channels: int, stride: int = 1):
        super().__init__()

        self.conv1 = nn.Conv2d(in_channels, out_channels, kernel_size=1, stride=1)
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.conv2 = nn.Conv2d(out_channels, out_channels, kernel_size=3, stride=stride, padding=1)
        self.bn2 = nn.BatchNorm2d(out_channels)
        self.conv3 = nn.Conv2d(out_channels, out_channels * self.expansion, kernel_size=1, stride=1)
        self.bn3 = nn.BatchNorm2d(out_channels * self.expansion)
        self.relu = nn.ReLU(inplace=True)

        self.shortcut = nn.Sequential()
        if stride != 1 or in_channels != out_channels * self.expansion:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels * self.expansion, kernel_size=1, stride=stride),
                nn.BatchNorm2d(out_channels * self.expansion)
            )

    def forward(self, x):
        residual = x
        out = self.relu(self.bn1(self.conv1(x)))
        out = self.relu(self.bn2(self.conv2(out)))
        out = self.bn3(self.conv3(out))

        out += self.shortcut(residual)
        out = self.relu(out)

        return out


class ResNet(nn.Module):
    def __init__(self, block, layers):
        super().__init__()
        self.in_channels = 64

        self.conv1 = nn.Conv2d(3, 64, kernel_size=7, stride=2, padding=3)
        self.bn1 = nn.BatchNorm2d(64)
        self.relu = nn.ReLU(inplace=True)
        self.maxpool = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)

        self.layer1 = self._make_layer(block, layers[0], 64)
        self.layer2 = self._make_layer(block, layers[1], 128, stride=2)
        self.layer3 = self._make_layer(block, layers[2], 256, stride=2)
        self.layer4 = self._make_layer(block, layers[3], 512, stride=2)

        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.fc = nn.Linear(512 * block.expansion, 512)

    def _make_layer(self, block, blocks, out_channels, stride=1):
        layers = []
        layers.append(block(self.in_channels, out_channels, stride))
        self.in_channels = out_channels * block.expansion
        for _ in range(1, blocks):
            layers.append(block(self.in_channels, out_channels))

        return nn.Sequential(*layers)

    def forward(self, x):
        x = self.relu(self.bn1(self.conv1(x)))
        x = self.maxpool(x)

        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        x = self.layer4(x)

        x = self.avgpool(x)
        x = x.view(x.size(0), -1)
        x = self.fc(x)

        return x


def ResNet18():
    return ResNet(BasicBlock, [2, 2, 2, 2])


def ResNet50():
    return ResNet(BottleneckBlock, [3, 4, 6, 3])


class VQAModel(nn.Module):
    def __init__(self, vocab_size: int, n_answer: int):
        super().__init__()
        self.resnet = ResNet18()
        self.text_encoder = nn.Linear(vocab_size, 512)

        self.fc = nn.Sequential(
            nn.Linear(1024, 512),
            nn.ReLU(inplace=True),
            nn.Linear(512, n_answer)
        )

    def forward(self, image, question):
        image_feature = self.resnet(image)  # 画像の特徴量
        question_feature = self.text_encoder(question)  # テキストの特徴量

        x = torch.cat([image_feature, question_feature], dim=1)
        x = self.fc(x)

        return x

model = VQAModel(vocab_size=bert_size, n_answer=500)
s_image = Tensor(np.random.uniform(size=(1, 3, 224, 224)))
print(s_image.shape)
s_question = Tensor(np.random.uniform(size=(1, 768)))
s_pred = model(s_image, s_question)
print(s_pred.shape)



# deviceの設定
set_seed(42)
device = "cuda" if torch.cuda.is_available() else "cpu"
print(device)

# dataloader / model
transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor()
])

train_dataset = VQADataset(df_path="/workspace/assets/train.json", image_dir="/workspace/assets/train2",dict_path="/workspace/assets/class_mapping.csv", transform=transform)
test_dataset = VQADataset(df_path="/workspace/assets/valid.json", image_dir="/workspace/assets/valid", transform=transform, answer=False)
test_dataset.update_dict(train_dataset)

train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=128, shuffle=True, num_workers=2, pin_memory=True)
test_loader = torch.utils.data.DataLoader(test_dataset, batch_size=1, shuffle=False, num_workers=2, pin_memory=True)

model = VQAModel(vocab_size=bert_size, n_answer=len(train_dataset.answer2idx)).to(device)

# optimizer / criterion

num_epoch = 5
criterion = nn.CrossEntropyLoss()
optimizer = torch.optim.Adam(model.parameters(), lr=0.0001, weight_decay=1e-5)

print(len(train_loader.dataset.idx2answer))
a = Tensor([1, 1])
a = a.numpy().tolist()
print(a)

print(len(test_loader))
#model = model.load_state_dict('/content/model.pth', model)

# 4. 学習の実装
def train(model, dataloader, optimizer, criterion, device):
    print(len(dataloader))
    print(device)
    model.to(device)
    model.train()

    total_loss = 0
    total_acc = 0
    simple_acc = 0
    count = 0

    start = time.time()
    for image, question, answers, mode_answer in dataloader:
        image, question, answer, mode_answer = \
            image.to(device), question.to(device), answers.to(device), mode_answer.to(device)

        pred = model(image, question)
        #print(question)
        #sample = pred.argmax(1).cpu().squeeze().numpy().tolist()
        #print(pred.shape, mode_answer.shape)
        #print(sample, mode_answer.squeeze())
        #print([dataloader.dataset.idx2answer[id] for id in sample])
        loss = criterion(pred, mode_answer.squeeze())

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        total_acc += VQA_criterion(pred.argmax(1), answers)  # VQA accuracy
        simple_acc += (pred.argmax(1) == mode_answer).float().mean().item()  # simple accuracy
        count += 1
        if count%10 == 0:
          print(f"batch {count}/{len(dataloader)}")

    return total_loss / len(dataloader), total_acc / len(dataloader), simple_acc / len(dataloader), time.time() - start


def eval(model, dataloader, optimizer, criterion, device):
    print(len(dataloader))
    print(device)
    model.to(device)
    model.eval()

    total_loss = 0
    total_acc = 0
    simple_acc = 0
    count = 0

    start = time.time()
    for image, question, answers, mode_answer in dataloader:
        image, question, answer, mode_answer = \
            image.to(device), question.to(device), answers.to(device), mode_answer.to(device)


        pred = model(image, question)
        loss = criterion(pred, mode_answer.squeeze())

        total_loss += loss.item()
        total_acc += VQA_criterion(pred.argmax(1), answers)  # VQA accuracy
        simple_acc += (pred.argmax(1) == mode_answer).mean().item()  # simple accuracy
        count += 1
        if count%10 == 0:
          print(f"batch {count}/{len(dataloader)}")


    return total_loss / len(dataloader), total_acc / len(dataloader), simple_acc / len(dataloader), time.time() - start

def main():


    # train model
    for epoch in range(num_epoch):
        train_loss, train_acc, train_simple_acc, train_time = train(model, train_loader, optimizer, criterion, device)
        print(f"【{epoch + 1}/{num_epoch}】\n"
              f"train time: {train_time:.2f} [s]\n"
              f"train loss: {train_loss:.4f}\n"
              f"train acc: {train_acc:.4f}\n"
              f"train simple acc: {train_simple_acc:.4f}")
    torch.save(model.state_dict(), "model.pth")
    # 提出用ファイルの作成
    model.eval()
    submission = []
    count = 0
    for image, question in test_loader:
        image, question = image.to(device), question.to(device)
        pred = model(image, question)
        pred = pred.argmax(1).cpu().item()
        submission.append(pred)
        count += 1
        if count % 1000 == 0:
          print(f"{count}/{len(test_loader)}")

    submission = [train_dataset.idx2answer[id] for id in submission]
    submission = np.array(submission)
    #torch.save(model.state_dict(), "model.pth")
    np.save("submission.npy", submission)

if __name__ == "__main__":
    main()
