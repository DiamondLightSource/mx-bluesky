from __future__ import annotations

from abc import abstractmethod
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeVar, cast

from dodal.beamline_specific_utils.i03 import beam_size_from_aperture
from dodal.devices.detector import DetectorParams
from dodal.devices.detector.det_resolution import resolution
from dodal.devices.synchrotron import SynchrotronMode

from mx_bluesky.common.external_interaction.callbacks.common.logging_callback import (
    format_doc_for_log,
)
from mx_bluesky.common.external_interaction.callbacks.common.plan_reactive_callback import (
    PlanReactiveCallback,
)
from mx_bluesky.common.external_interaction.ispyb.data_model import (
    DataCollectionInfo,
    DataCollectionPositionInfo,
    ScanDataInfo,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_store import (
    IspybIds,
    StoreInIspyb,
)
from mx_bluesky.common.external_interaction.ispyb.ispyb_utils import get_ispyb_config
from mx_bluesky.common.parameters.components import DiffractionExperimentWithSample
from mx_bluesky.common.parameters.constants import DocDescriptorNames
from mx_bluesky.common.utils.log import ISPYB_ZOCALO_CALLBACK_LOGGER, set_dcgid_tag
from mx_bluesky.common.utils.utils import convert_eV_to_angstrom

D = TypeVar("D")
if TYPE_CHECKING:
    from event_model.documents import Event, EventDescriptor, RunStart, RunStop


def _update_based_on_energy(
    doc: Event,
    detector_params: DetectorParams,
    data_collection_info: DataCollectionInfo,
):
    """If energy has been read as part of this reading then add it into the data
    collection info along with the other fields that depend on it."""
    if energy_kev := doc["data"].get("dcm-energy_in_kev", None):
        energy_ev = energy_kev * 1000
        wavelength_angstroms = convert_eV_to_angstrom(energy_ev)
        data_collection_info.wavelength = wavelength_angstroms
        data_collection_info.resolution = resolution(
            detector_params,
            wavelength_angstroms,
            detector_params.detector_distance,
        )
    return data_collection_info


class BaseISPyBCallback(PlanReactiveCallback):
    def __init__(
        self,
        *,
        emit: Callable[..., Any] | None = None,
    ) -> None:
        """Subclasses should run super().__init__() with parameters, then set
        self.ispyb to the type of ispyb relevant to the experiment and define the type
        for self.ispyb_ids."""
        ISPYB_ZOCALO_CALLBACK_LOGGER.debug("Initialising ISPyB callback")
        super().__init__(log=ISPYB_ZOCALO_CALLBACK_LOGGER, emit=emit)
        self._oav_snapshot_event_idx: int = 0
        self.params: DiffractionExperimentWithSample | None = None
        self.ispyb: StoreInIspyb
        self.descriptors: dict[str, EventDescriptor] = {}
        self.ispyb_config = get_ispyb_config()
        ISPYB_ZOCALO_CALLBACK_LOGGER.info(
            f"Using ISPyB configuration from {self.ispyb_config}"
        )
        if not self.ispyb_config or not Path(self.ispyb_config).is_absolute():
            ISPYB_ZOCALO_CALLBACK_LOGGER.warning(
                f"{self.__class__} using dev ISPyB config: {self.ispyb_config}. If you"
                "want to use the real database, please set the ISPYB_CONFIG_PATH "
                "environment variable."
            )
        self.uid_to_finalize_on: str | None = None
        self.ispyb_ids: IspybIds = IspybIds()
        self.log = ISPYB_ZOCALO_CALLBACK_LOGGER

    def activity_gated_start(self, doc: RunStart):
        self._oav_snapshot_event_idx = 0
        return self._tag_doc(doc)

    def activity_gated_descriptor(self, doc: EventDescriptor):
        self.descriptors[doc["uid"]] = doc
        return self._tag_doc(doc)

    def activity_gated_event(self, doc: Event) -> Event:
        """Subclasses should extend this to add a call to set_dcig_tag from
        hyperion.log"""
        ISPYB_ZOCALO_CALLBACK_LOGGER.debug("ISPyB handler received event document.")
        assert self.ispyb is not None, "ISPyB deposition wasn't initialised!"
        assert self.params is not None, "ISPyB handler didn't receive parameters!"

        event_descriptor = self.descriptors.get(doc["descriptor"])
        if event_descriptor is None:
            ISPYB_ZOCALO_CALLBACK_LOGGER.warning(
                f"Ispyb handler {self} received event doc {format_doc_for_log(doc)} and "
                "has no corresponding descriptor record"
            )
            return doc
        match event_descriptor.get("name"):
            case DocDescriptorNames.HARDWARE_READ_PRE:
                scan_data_infos = self._handle_ispyb_hardware_read(doc)
            case DocDescriptorNames.HARDWARE_READ_DURING:
                scan_data_infos = self._handle_ispyb_transmission_flux_read(doc)
            case _:
                return self._tag_doc(doc)
        self.ispyb_ids = self.ispyb.update_deposition(self.ispyb_ids, scan_data_infos)
        ISPYB_ZOCALO_CALLBACK_LOGGER.info(f"Received ISPYB IDs: {self.ispyb_ids}")
        return self._tag_doc(doc)

    def _handle_ispyb_hardware_read(self, doc) -> Sequence[ScanDataInfo]:
        assert self.params, "Event handled before activity_gated_start received params"
        ISPYB_ZOCALO_CALLBACK_LOGGER.info(
            "ISPyB handler received event from read hardware"
        )
        synchrotron_mode = doc["data"]["synchrotron-synchrotron_mode"]
        assert isinstance(synchrotron_mode, SynchrotronMode)

        hwscan_data_collection_info = DataCollectionInfo(
            undulator_gap1=doc["data"]["undulator-current_gap"],
            synchrotron_mode=synchrotron_mode.value,
            slitgap_horizontal=doc["data"]["s4_slit_gaps-xgap"],
            slitgap_vertical=doc["data"]["s4_slit_gaps-ygap"],
        )
        hwscan_data_collection_info = _update_based_on_energy(
            doc, self.params.detector_params, hwscan_data_collection_info
        )
        hwscan_position_info = DataCollectionPositionInfo(
            pos_x=float(doc["data"]["smargon-x"]),
            pos_y=float(doc["data"]["smargon-y"]),
            pos_z=float(doc["data"]["smargon-z"]),
        )
        scan_data_infos = self.populate_info_for_update(
            hwscan_data_collection_info, hwscan_position_info, self.params
        )
        ISPYB_ZOCALO_CALLBACK_LOGGER.info(
            "Updating ispyb data collection after hardware read."
        )
        return scan_data_infos

    def _handle_ispyb_transmission_flux_read(self, doc) -> Sequence[ScanDataInfo]:
        assert self.params
        aperture = doc["data"]["aperture_scatterguard-selected_aperture"]
        aperture_radius = doc["data"]["aperture_scatterguard-radius"]
        beamsize = beam_size_from_aperture(aperture_radius)
        beamsize_x_mm = beamsize.x_um / 1000 if beamsize.x_um else None
        beamsize_y_mm = beamsize.y_um / 1000 if beamsize.y_um else None
        hwscan_data_collection_info = DataCollectionInfo(
            beamsize_at_samplex=beamsize_x_mm,
            beamsize_at_sampley=beamsize_y_mm,
            focal_spot_size_at_samplex=beamsize_x_mm,
            focal_spot_size_at_sampley=beamsize_y_mm,
            flux=doc["data"]["flux-flux_reading"],
        )
        if transmission := doc["data"]["attenuator-actual_transmission"]:
            # Ispyb wants the transmission in a percentage, we use fractions
            hwscan_data_collection_info.transmission = transmission * 100
        hwscan_data_collection_info = _update_based_on_energy(
            doc, self.params.detector_params, hwscan_data_collection_info
        )
        scan_data_infos = self.populate_info_for_update(
            hwscan_data_collection_info, None, self.params
        )
        ISPYB_ZOCALO_CALLBACK_LOGGER.info(
            "Updating ispyb data collection after flux read."
        )
        self.append_to_comment(f"Aperture: {aperture}. ")
        return scan_data_infos

    @abstractmethod
    def populate_info_for_update(
        self,
        event_sourced_data_collection_info: DataCollectionInfo,
        event_sourced_position_info: DataCollectionPositionInfo | None,
        params: DiffractionExperimentWithSample,
    ) -> Sequence[ScanDataInfo]:
        pass

    def activity_gated_stop(self, doc: RunStop) -> RunStop:
        """Subclasses must check that they are recieving a stop document for the correct
        uid to use this method!"""
        assert self.ispyb is not None, (
            "ISPyB handler received stop document, but deposition object doesn't exist!"
        )
        ISPYB_ZOCALO_CALLBACK_LOGGER.debug("ISPyB handler received stop document.")
        exit_status = (
            doc.get("exit_status") or "Exit status not available in stop document!"
        )
        reason = doc.get("reason") or ""
        set_dcgid_tag(None)
        try:
            self.ispyb.end_deposition(self.ispyb_ids, exit_status, reason)
        except Exception as e:
            ISPYB_ZOCALO_CALLBACK_LOGGER.warning(
                f"Failed to finalise ISPyB deposition on stop document: {format_doc_for_log(doc)} with exception: {e}"
            )
        return self._tag_doc(doc)

    def _append_to_comment(self, id: int, comment: str) -> None:
        assert self.ispyb is not None
        try:
            self.ispyb.append_to_comment(id, comment)
        except TypeError:
            ISPYB_ZOCALO_CALLBACK_LOGGER.warning(
                "ISPyB deposition not initialised, can't update comment."
            )

    def append_to_comment(self, comment: str):
        for id in self.ispyb_ids.data_collection_ids:
            self._append_to_comment(id, comment)

    def _tag_doc(self, doc: D) -> D:
        assert isinstance(doc, dict)
        if self.ispyb_ids:
            doc["ispyb_dcids"] = self.ispyb_ids.data_collection_ids
        return cast(D, doc)
