import torch
import torch.nn as nn

from torch.utils.data import DataLoader
from torchvision import datasets, transforms
class Convextnet(nn.Module):
    def __init__(self,numclasses=5,type="Tiny"):
        super().__init__()
        self.num=numclasses
        if type=="Tiny":
            from torchvision.models import convnext_tiny, ConvNeXt_Tiny_Weights
            weights = ConvNeXt_Tiny_Weights.IMAGENET1K_V1

            self.model = convnext_tiny(weights=weights)
        elif type=="Small":
            from torchvision.models import convnext_small, ConvNeXt_Small_Weights
            weights = ConvNeXt_Small_Weights.IMAGENET1K_V1
            self.model = convnext_small(weights=weights)
        else:
             from torchvision.models import convnext_base, ConvNeXt_Base_Weights
             weights = ConvNeXt_Base_Weights.IMAGENET1K_V1
             self.model = convnext_base(weights=weights)

        in_features =self. model.classifier[2].in_features
        self.model.classifier[2] = nn.Linear(in_features, self.num)

    def forward(self,x):
        return self.model(x)

       
