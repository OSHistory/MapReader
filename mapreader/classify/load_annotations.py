#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from decimal import Decimal
from typing import Callable, Optional, Union

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image
from sklearn.model_selection import train_test_split
from torch import Tensor
from torch.utils.data import DataLoader, Sampler, WeightedRandomSampler
from torchvision.transforms import Compose

from .datasets import PatchDataset


class AnnotationsLoader:
    def __init__(self):
        """
        A Class for loading annotations and preparing datasets and dataloaders for use in training/validation of a model.
        """
        self.annotations = pd.DataFrame()
        self.reviewed = pd.DataFrame()
        self.id_col = None
        self.patch_paths_col = None
        self.label_col = None
        self.datasets = None

    def load(
        self,
        annotations: Union[str, pd.DataFrame],
        delimiter: Optional[str] =",",
        images_dir: Optional[str] = None,
        remove_broken: Optional[bool] = True,
        ignore_broken: Optional[bool] = False,
        id_col: Optional[str] = "image_id",
        patch_paths_col: Optional[str] = "image_path",
        label_col: Optional[str] = "label",
        append: Optional[bool] = True,
        scramble_frame: Optional[bool] = False,
        reset_index: Optional[bool] = False,
    ):
        """Loads annotations from a csv file or dataframe and can be used to set the ``id_col``, ``patch_paths_col`` and ``label_col`` attributes.

        Parameters
        ----------
        annotations : Union[str, pd.DataFrame]
            The annotations.
            Can either be the path to a csv file or a pandas.DataFrame.
        delimiter : Optional[str], optional
            The delimiter to use when loading the csv file as a dataframe, by default ",".
        images_dir : Optional[str], optional
            The path to the directory in which patches are stored.
            This argument should be passed if image paths are different from the path saved in annotations dataframe/csv.
            If None, no updates will be made to the image paths in the annotations dataframe/csv. 
            By default None.
        remove_broken : Optional[bool], optional
            Whether to remove annotations with broken image paths.
            If False, annotations with broken paths will remain in annotations dataframe and may cause issues!
            By default True.
        ignore_broken : Optional[bool], optional
            Whether to ignore broken image paths (only valid if remove_broken=False).
            If True, annotations with broken paths will remain in annotations dataframe and no error will be raised. This may cause issues!
            If False, annotations with broken paths will raise error. By default, False.
        id_col : Optional[str], optional
            The name of the column which contains the image IDs, by default "image_id".
        patch_paths_col : Optional[str], optional
            The name of the column containing the image paths, by default "image_path".
        label_col : Optional[str], optional
            The name of the column containing the image labels, by default "label".
        append : Optional[bool], optional
            Whether to append the annotations to a pre-existing ``annotations`` dataframe.
            If False, existing dataframe will be overwritten.
            By default True.
        scramble_frame : Optional[bool], optional
            Whether to shuffle the rows of the dataframe, by default False.
        reset_index : Optional[bool], optional
            Whether to reset the index of the dataframe (e.g. after shuffling), by default False.

        Raises
        ------
        ValueError
            If ``annotations`` is passed as something other than a string or pd.DataFrame.
        """

        if not self.id_col:
            self.id_col = id_col
        elif self.id_col != id_col:
            print(
                f'[WARNING] ID column was previously "{self.id_col}, but will now be set to {id_col}.'
            )

        if not self.patch_paths_col:
            self.patch_paths_col = patch_paths_col
        elif self.patch_paths_col != patch_paths_col:
            print(
                f'[WARNING] Patch paths column was previously "{self.patch_paths_col}, but will now be set to {patch_paths_col}.'
            )

        if not self.label_col:
            self.label_col = label_col
        elif self.label_col != label_col:
            print(
                f'[WARNING] Label column was previously "{self.label_col}, but will now be set to {label_col}.'
            )

        if not isinstance(annotations, (str, pd.DataFrame)):
            raise ValueError(
                "[ERROR] Please pass ``annotations`` as a string (path to csv file) or pd.DataFrame."
            )
        if isinstance(annotations, str):
            annotations = self._load_annotations_csv(
                annotations, delimiter, scramble_frame, reset_index
            )

        if images_dir:
            abs_images_dir = os.path.abspath(images_dir)
            annotations[self.patch_paths_col] = annotations[self.id_col].apply(lambda x: os.path.join(abs_images_dir, x))

        annotations = annotations.astype(
            {self.label_col: str}
        )  # ensure labels are interpreted as strings

        if append:
            self.annotations = pd.concat([self.annotations, annotations])
        else:
            self.annotations = annotations

        self._check_patch_paths(remove_broken=remove_broken, ignore_broken=ignore_broken)

        unique_labels = self.annotations[self.label_col].unique().tolist()
        self.unique_labels = unique_labels
        self.annotations["label_index"] = self.annotations[self.label_col].apply(
            self._get_label_index
        )

        labels_map = {i: label for i, label in enumerate(unique_labels)}
        self.labels_map = labels_map

        print(self)

    def _load_annotations_csv(
        self,
        annotations: str,
        delimiter: Optional[str] = ",",
        scramble_frame: Optional[bool] = False,
        reset_index: Optional[bool] = False,
    ) -> pd.DataFrame:
        """Loads annotations from a csv file.

        Parameters
        ----------
        annotations : str
            The path to the annotations csv file.
        delimiter : Optional[str], optional
            The delimiter to use when loading the csv file as a dataframe, by default ",".
        scramble_frame : Optional[bool], optional
            Whether to shuffle the rows of the dataframe, by default False.
        reset_index : Optional[bool], optional
            Whether to reset the index of the dataframe (e.g. after shuffling), by default False.

        Returns
        -------
        pd.DataFrame
            Dataframe containing the annotations.

        Raises
        ------
        ValueError
            If ``annotations`` is passed as something other than a string or pd.DataFrame.
        """

        if os.path.isfile(annotations):
            print(f'[INFO] Reading "{annotations}"')
            annotations = pd.read_csv(annotations, sep=delimiter, index_col=0)
        else:
            raise ValueError(f'[ERROR] "{annotations}" cannot be found.')

        if scramble_frame:
            annotations = annotations.sample(frac=1)
        if reset_index:
            annotations.reset_index(drop=True, inplace=True)

        annotations.drop_duplicates(subset=self.id_col, inplace=True, keep="first")
        return annotations

    def _check_patch_paths(
            self,
            remove_broken: Optional[bool] = True,
            ignore_broken: Optional[bool] = False,
        ) -> None:

        """
        Checks the file paths of annotations and manages broken paths.

        Parameters
        ----------
        remove_broken : Optional[bool], optional
            Whether to remove annotations with broken image paths.
            If False, annotations with broken paths will remain in annotations dataframe and may cause issues!
            By default True.
        ignore_broken : Optional[bool], optional
            Whether to ignore broken image paths (only valid if remove_broken=False).
            If True, annotations with broken paths will remain in annotations dataframe and no error will be raised. This may cause issues!
        """

        if len(self.annotations) == 0:
            return

        broken_paths = []
        for i, patch_path in self.annotations[self.patch_paths_col].items():
            if not os.path.exists(patch_path):
                broken_paths.append(patch_path)
                if remove_broken:
                    self.annotations.drop(i, inplace=True)
        
        if len(broken_paths)!=0: # write broken paths to text file
            with open('broken_files.txt', 'w') as f:
                for broken_path in broken_paths:
                    f.write(f"{broken_path}\n")

            print(f"[WARNING] {len(broken_paths)} files cannot be found.\n\
Check '{os.path.abspath('broken_paths.txt')}' for more details and, if possible, update your file paths using the 'images_dir' argument.")

            if remove_broken:
                if len(self.annotations)==0:
                    raise ValueError("[ERROR] No annotations remaining. \
Please check your files exist and, if possible, update your file paths using the 'images_dir' argument.")
                else:
                    print(f"[INFO] Annotations with broken file paths have been removed.\n\
Number of annotations remaining: {len(self.annotations)}")
            
            else: # raise error for 'remove_broken=False'
                if ignore_broken:
                    print(f"[WARNING] Continuing with {len(broken_paths)} broken file paths.")
                else:
                    raise ValueError(f"[ERROR] {len(broken_paths)} files cannot be found.")

    def show_patch(self, patch_id: str) -> None:
        """
        Display a patch and its label.

        Parameters
        ----------
        patch_id : str
            The image ID of the patch to show.

        Returns
        -------
        None
        """

        if len(self.annotations) == 0:
            raise ValueError("[ERROR] No annotations loaded.")

        patch_row = self.annotations[self.annotations[self.id_col] == patch_id]
        patch_path = patch_row[self.patch_paths_col].values[0]
        patch_label = patch_row[self.label_col].values[0]
        try:
            img = Image.open(patch_path)
        except FileNotFoundError as e:
            e.add_note(f'[ERROR] File could not be found: "{patch_path}".\n\n\
Please check your image paths in your annonations.csv file and update them if necessary.')

        plt.imshow(img)
        plt.axis("off")
        plt.title(patch_label)
        plt.show()

    def print_unique_labels(self) -> None:
        """Prints unique labels

        Raises
        ------
        ValueError
            If no annotations are found.
        """
        if len(self.annotations) == 0:
            raise ValueError("[ERROR] No annotations loaded.")

        print(f"[INFO] Unique labels: {self.unique_labels}")

    def review_labels(
        self,
        label_to_review: Optional[str] = None,
        chunks: Optional[int] = 8 * 3,
        num_cols: Optional[int] = 8,
        exclude_df: Optional[pd.DataFrame] = None,
        include_df: Optional[pd.DataFrame] = None,
        deduplicate_col: Optional[str] = "image_id",
    ) -> None:
        """
        Perform image review on annotations and update labels for a given
        label or all labels.

        Parameters
        ----------
        label_to_review : str, optional
            The target label to review. If not provided, all labels will be
            reviewed, by default ``None``.
        chunks : int, optional
            The number of images to display at a time, by default ``24``.
        num_cols : int, optional
            The number of columns in the display, by default ``8``.
        exclude_df : pandas.DataFrame, optional
            A DataFrame of images to exclude from review, by default ``None``.
        include_df : pandas.DataFrame, optional
            A DataFrame of images to include for review, by default ``None``.
        deduplicate_col : str, optional
            The column to use for deduplicating reviewed images, by default
            ``"image_id"``.

        Returns
        -------
        None

        Notes
        ------
        This method reviews images with their corresponding labels and allows
        the user to change the label for each image.

        Updated labels are saved in ``self.annotations`` and in a newly created ``self.reviewed`` DataFrame.
        If ``exclude_df`` is provided, images found in this df are skipped in the review process.
        If ``include_df`` is provided, only images found in this df are reviewed.
        The ``self.reviewed`` DataFrame is deduplicated based on the ``deduplicate_col``.
        """
        if len(self.annotations) == 0:
            raise ValueError("[ERROR] No annotations loaded.")

        if label_to_review:
            annots2review = self.annotations[
                self.annotations[self.label_col] == label_to_review
            ]
            annots2review.reset_index(inplace=True, drop=True)
        else:
            annots2review = self.annotations
            annots2review.reset_index(inplace=True, drop=True)

        if exclude_df is not None:
            if isinstance(exclude_df, pd.DataFrame):
                merged_df = pd.merge(
                    annots2review, exclude_df, how="left", indicator=True
                )
                annots2review = merged_df[merged_df["_merge"] == "left_only"].drop(
                    columns="_merge"
                )
                annots2review.reset_index(inplace=True, drop=True)
            else:
                raise ValueError("[ERROR] ``exclude_df`` must be a pandas dataframe.")

        if include_df is not None:
            if isinstance(include_df, pd.DataFrame):
                annots2review = pd.merge(annots2review, include_df, how="right")
                annots2review.reset_index(inplace=True, drop=True)
            else:
                raise ValueError("[ERROR] ``include_df`` must be a pandas dataframe.")

        image_idx = 0
        while image_idx < len(annots2review):
            print('[INFO] Type "exit", "end" or "stop" to exit.')
            print(
                f"[INFO] Showing {image_idx}-{image_idx+chunks} out of {len(annots2review)}."  # noqa
            )
            plt.figure(figsize=(num_cols * 3, (chunks // num_cols) * 3))
            counter = 1
            iter_ids = []
            while (counter <= chunks) and (image_idx < len(annots2review)):
                # The first term is just a ceiling division, equivalent to:
                # from math import ceil
                # int(ceil(chunks / num_cols))
                plt.subplot((chunks // num_cols), num_cols, counter)
                patch_path = annots2review.iloc[image_idx][self.patch_paths_col]
                try:
                    img = Image.open(patch_path)
                except FileNotFoundError as e:
                    e.add_note(f'[ERROR] File could not be found: "{patch_path}".\n\n\
Please check your image paths and update them if necessary.')
                plt.imshow(img)
                plt.xticks([])
                plt.yticks([])
                plt.title(
                    f"{annots2review.iloc[image_idx][self.label_col]} | id: {annots2review.iloc[image_idx].name}"  # noqa
                )
                iter_ids.append(annots2review.iloc[image_idx].name)
                # Add to reviewed
                self.reviewed = self.reviewed.append(annots2review.iloc[image_idx])
                try:
                    self.reviewed.drop_duplicates(subset=[deduplicate_col])
                except Exception:
                    pass
                counter += 1
                image_idx += 1
            plt.show()

            print(f"[INFO] IDs of current patches: {iter_ids}")
            q = "\nEnter IDs, comma separated (or press enter to continue): "
            user_input_ids = input(q)

            while user_input_ids.strip().lower() not in [
                "",
                "exit",
                "end",
                "stop",
            ]:
                list_input_ids = user_input_ids.split(",")
                print(
                    f"[INFO] Options for labels (or create a new label):{list(self.annotations[self.label_col].unique())}"
                )
                input_label = input("Enter new label:  ")

                for input_id in list_input_ids:
                    input_id = int(input_id)
                    # Change both annotations and reviewed
                    self.annotations.loc[input_id, self.label_col] = input_label
                    self.reviewed.loc[input_id, self.label_col] = input_label
                    # Update label indices
                    self.annotations.loc[
                        input_id, "label_index"
                    ] = self._get_label_index(input_label)
                    self.reviewed.loc[input_id, "label_index"] = self._get_label_index(
                        input_label
                    )
                    assert (
                        self.annotations[self.label_col].value_counts().tolist()
                        == self.annotations["label_index"].value_counts().tolist()
                    )
                    print(
                        f'[INFO] Image {input_id} has been relabelled as "{input_label}"'
                    )

                user_input_ids = input(q)

            if user_input_ids.lower() in ["exit", "end", "stop"]:
                break

        print("[INFO] Exited.")

    def show_sample(self, label_to_show: str, num_samples: Optional[int] = 9) -> None:
        """Show a random sample of images with the specified label (tar_label).

        Parameters
        ----------
        label_to_show : str, optional
            The label of the images to show.
        num_sample : int, optional
            The number of images to show.
            If ``None``, all images with the specified label will be shown. Default is ``9``.

        Returns
        -------
        None
        """
        if len(self.annotations) == 0:
            raise ValueError("[ERROR] No annotations loaded.")

        annot2plot = self.annotations[self.annotations[self.label_col] == label_to_show]
        annot2plot = annot2plot.sample(frac=1)
        annot2plot.reset_index(drop=True, inplace=True)

        num_samples = min(len(annot2plot), num_samples)

        plt.figure(figsize=(8, num_samples))
        for i in range(num_samples):
            plt.subplot(int(num_samples / 2.0), 3, i + 1)
            patch_path = annot2plot.iloc[i][self.patch_paths_col]
            try:
                img = Image.open(patch_path)
            except FileNotFoundError:
                raise FileNotFoundError(f'[ERROR] File could not be found: "{patch_path}".\n\n\
Please check your image paths and update them if necessary.')
            plt.imshow(img)
            plt.axis("off")
            plt.title(annot2plot.iloc[i][self.label_col])
        plt.show()

    def create_datasets(
        self,
        frac_train: Optional[float] = 0.70,
        frac_val: Optional[float] = 0.15,
        frac_test: Optional[float] = 0.15,
        random_state: Optional[int] = 1364,
        train_transform: Optional[Union[str, Compose, Callable]] = "train",
        val_transform: Optional[Union[str, Compose, Callable]] = "val",
        test_transform: Optional[Union[str, Compose, Callable]] = "test",
    ) -> None:
        """
        Splits the dataset into three subsets: training, validation, and test sets (DataFrames) and saves them as a dictionary in ``self.datasets``.

        Parameters
        ----------
        frac_train : float, optional
            Fraction of the dataset to be used for training.
            By default ``0.70``.
        frac_val : float, optional
            Fraction of the dataset to be used for validation.
            By default ``0.15``.
        frac_test : float, optional
            Fraction of the dataset to be used for testing.
            By default ``0.15``.
        random_state : int, optional
            Random seed to ensure reproducibility. The default is ``1364``.
        train_transform: str, tochvision.transforms.Compose or Callable, optional
            The transform to use on the training dataset images.
            Options are "train", "test" or "val" or, a callable object (e.g. a torchvision transform or torchvision.transforms.Compose).
            By default "train".
        val_transform: str, tochvision.transforms.Compose or Callable, optional
            The transform to use on the validation dataset images.
            Options are "train", "test" or "val" or, a callable object (e.g. a torchvision transform or torchvision.transforms.Compose).
            By default "val".
        test_transform: str, tochvision.transforms.Compose or Callable, optional
            The transform to use on the test dataset images.
            Options are "train", "test" or "val" or, a callable object (e.g. a torchvision transform or torchvision.transforms.Compose).
            By default "test".


        Raises
        ------
        ValueError
            If the sum of fractions of training, validation and test sets does
            not add up to 1.

        Returns
        -------
        None

        Notes
        -----
        This method saves the split datasets as a dictionary in ``self.datasets``.

        Following fractional ratios provided by the user, where each subset is
        stratified by the values in a specific column (that is, each subset has
        the same relative frequency of the values in the column). It performs
        this splitting by running ``train_test_split()`` twice.

        See ``PatchDataset`` for more information on transforms.
        """
        if len(self.annotations) == 0:
            raise ValueError("[ERROR] No annotations loaded.")

        frac_train = Decimal(str(frac_train))
        frac_val = Decimal(str(frac_val))
        frac_test = Decimal(str(frac_test))

        if sum([frac_train + frac_val + frac_test]) != 1:
            raise ValueError(
                f"[ERROR] ``frac_train`` ({frac_train}), ``frac_val`` ({frac_val}) and ``frac_test`` ({frac_test}) do not add up to 1."
            )  # noqa

        labels = self.annotations[self.label_col]

        # Split original dataframe into train and temp (val+test) dataframes.
        df_train, df_temp, _, labels_temp = train_test_split(
            self.annotations,
            labels,
            stratify=labels,
            test_size=float(1 - frac_train),
            random_state=random_state,
        )

        if frac_test != 0:
            # Split the temp dataframe into val and test dataframes.
            relative_frac_test = Decimal(frac_test / (frac_val + frac_test))
            relative_frac_test = relative_frac_test.quantize(Decimal("0.001"))
            df_val, df_test, _, _ = train_test_split(
                df_temp,
                labels_temp,
                stratify=labels_temp,
                test_size=float(relative_frac_test),
                random_state=random_state,
            )
            assert len(self.annotations) == len(df_train) + len(df_val) + len(df_test)

        else:
            df_val = df_temp
            df_test = None
            assert len(self.annotations) == len(df_train) + len(df_val)

        train_dataset = PatchDataset(
            df_train,
            train_transform,
            patch_paths_col=self.patch_paths_col,
            label_col=self.label_col,
            label_index_col="label_index",
        )
        val_dataset = PatchDataset(
            df_val,
            val_transform,
            patch_paths_col=self.patch_paths_col,
            label_col=self.label_col,
            label_index_col="label_index",
        )
        if df_test is not None:
            test_dataset = PatchDataset(
                df_test,
                test_transform,
                patch_paths_col=self.patch_paths_col,
                label_col=self.label_col,
                label_index_col="label_index",
                )
            datasets = {"train": train_dataset, "val": val_dataset, "test": test_dataset}
        
        else:
            datasets = {"train": train_dataset, "val": val_dataset}

        dataset_sizes = {
            set_name: len(datasets[set_name]) for set_name in datasets.keys()
        }

        self.datasets = datasets
        self.dataset_sizes = dataset_sizes

        print(
            f'[INFO] Number of annotations in each set:')
        for set_name in datasets.keys():
            print(f"    - {set_name}:   {dataset_sizes[set_name]}")

    def create_dataloaders(
        self,
        batch_size: Optional[int] = 16,
        sampler: Optional[Union[Sampler, str, None]] = "default",
        shuffle: Optional[bool] = False,
        num_workers: Optional[int] = 0,
        **kwargs,
    ) -> None:
        """Creates a dictionary containing PyTorch dataloaders
        saves it to as ``self.dataloaders`` and returns it.

        Parameters
        ----------
        batch_size : int, optional
            The batch size to use for the dataloader. By default ``16``.
        sampler : Sampler, str or None, optional
            The sampler to use when creating batches from the training dataset.
        shuffle : bool, optional
            Whether to shuffle the dataset during training. By default ``False``.
        num_workers : int, optional
            The number of worker threads to use for loading data. By default ``0``.
        **kwds :
            Additional keyword arguments to pass to PyTorch's ``DataLoader`` constructor.

        Returns
        --------
        Dict
            Dictionary containing dataloaders.

        Notes
        -----
        ``sampler`` will only be applied to the training dataset (datasets["train"]).
        """
        if not self.datasets:
            print(
                "[INFO] Creating datasets using default train/val/test split of 0.7:0.15:0.15 and default transformations."
            )
            self.create_datasets()

        datasets = self.datasets

        if isinstance(sampler, str):
            if sampler == "default":
                print("[INFO] Using default sampler.")
                sampler = self._define_sampler()
            else:
                raise ValueError(
                    '[ERROR] ``sampler`` can only be a PyTorch sampler, ``"default"`` or ``None``.'
                )

        if sampler and shuffle:
            print("[INFO] ``sampler`` is defined so train dataset will be un-shuffled.")

        dataloaders = {
            set_name: DataLoader(
                datasets[set_name],
                batch_size=batch_size,
                sampler=sampler if set_name == "train" else None,
                shuffle=False if set_name == "train" else shuffle,
                num_workers=num_workers,
                **kwargs,
            )
            for set_name in datasets.keys()
        }

        self.dataloaders = dataloaders

        return dataloaders

    def _define_sampler(self):
        """Defines a weighted random sampler for the training dataset.
        Weighting are proportional to the reciprocal of number of instances of each label.

        Returns
        -------
        torch.utils.data.WeightedRandomSampler
            The sampler

        Raises
        ------
        ValueError
            If "train" cannot be found in ``self.datasets.keys()``.
        """
        if not self.datasets:
            self.create_datasets()

        datasets = self.datasets

        if "train" in datasets.keys():
            value_counts = (
                datasets["train"].patch_df[self.label_col].value_counts().to_list()
            )
            weights = np.reciprocal(Tensor(value_counts))
            weights = weights.double()
            sampler = WeightedRandomSampler(
                weights[datasets["train"].patch_df["label_index"].tolist()],
                num_samples=len(datasets["train"].patch_df),
            )

        else:
            raise ValueError('[ERROR] "train" should be one the dataset names.')

        return sampler

    def _get_label_index(self, label: str) -> int:
        """Gets the index of a label.

        Parameters
        ----------
        label : str
            A label from the ``label_col`` of the ``patch_df``.

        Returns
        -------
        int
            The index of the label.

        Notes
        -----
        Used to generate the ``label_index`` column.

        """
        return self.unique_labels.index(label)

    def __str__(self):
        print(f"[INFO] Number of annotations:   {len(self.annotations)}\n")
        if len(self.annotations) > 0:
            value_counts = self.annotations[self.label_col].value_counts()
            print(
                f'[INFO] Number of instances of each label (from column "{self.label_col}"):'
            )
            for label, count in value_counts.items():
                print(f"    - {label}:  {count}")
        return ""
