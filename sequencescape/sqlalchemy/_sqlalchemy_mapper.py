from typing import Callable, Union, List, Any, Tuple

from sqlalchemy import Column

from sequencescape.enums import Property
from sequencescape.mapper import Mapper, LibraryMapper, MultiplexedLibraryMapper, SampleMapper, WellMapper, StudyMapper
from sequencescape.model import Model, Library, MultiplexedLibrary, Sample, Well, Study
from sequencescape.sqlalchemy._sqlalchemy_model_converter import convert_to_sqlalchemy_model, convert_to_popo_model, \
    convert_to_popo_models, get_equivalent_sqlalchemy_model_type
from sequencescape.sqlalchemy._sqlalchemy_database_connector import SQLAlchemyDatabaseConnector
from sequencescape.sqlalchemy._sqlalchemy_model import SQLAlchemyModel, SQLAlchemyStudySamplesLink, SQLAlchemyIsCurrent


class SQLAlchemyMapper(Mapper):
    def __init__(self, database_connector: SQLAlchemyDatabaseConnector, model_type: type):
        """
        Default constructor.
        :param database_connector: the object through which database connections can be made
        :param model_type: the type of the model that the mapper is used for
        """
        if not model_type:
            raise ValueError("Model type must be specified through `model_type` parameter")
        if not issubclass(model_type, Model):
            raise ValueError("Model type (%s) must be a subclass of `Model`" % model_type)

        self._type_cache = None
        self._model_type = model_type
        self._database_connector = database_connector

    def add(self, models: Union[Model, List[Model]]):
        if models is None:
            raise ValueError("Cannot add `None`")
        if not isinstance(models, list):
            models = [models]

        session = self._get_database_connector().create_session()
        for model in models:
            sqlalchemy_model = convert_to_sqlalchemy_model(model)
            session.add(sqlalchemy_model)
        session.commit()

    def get_all(self) -> List[Model]:
        query_model = self._get_sqlalchemy_model_type()
        session = self._get_database_connector().create_session()
        result = session.query(query_model). \
            filter(query_model.is_current == 1).all()
        session.close()
        assert isinstance(result, list)
        return result

    def _get_by_property_value_list(
            self, property: Property, values: Union[Any, List[Any]]) -> Union[Model, List[Model]]:
        if not isinstance(values, list):
            values = [values]
        result = self._get_by_property(property, values)
        if len(values) == 1:
            return convert_to_popo_model(result[0] if len(result) > 0 else None)
        else:
            return convert_to_popo_models(result)

    def _get_by_property_value_tuple(
            self, property_value_tuples: Union[Tuple, List[Tuple[Property, Any]]]) -> Union[Model, List[Model]]:
        if not isinstance(property_value_tuples, list):
            property_value_tuples = [property_value_tuples]
        results = []
        for property, value in property_value_tuples:
            try:
                result = self.get_by_property_value(property, value)
            except ValueError:
                print("Multiple entities with the same id found in the database")
            else:
                results.append(result)
        return results[0] if len(property_value_tuples) == 1 else results

    def _get_by_property(self, property: Property, required_property_values: List[Any]) -> List[Model]:
        """
        Gets many that have a property, defined by a given property selector, that matches a given value.
        :param property: TODO
        :param required_property_values: the property must match this value to be selected
        :return: models of the rows that are matched
        """
        # FIXME: Should this always limit `is_current` to 1?
        if not issubclass(self._get_sqlalchemy_model_type(), SQLAlchemyIsCurrent):
            raise ValueError(
                "Not possible to get instances of type %s by name as the query required `is_current` property"
                    % self._get_model_type())

        query_model = self._get_sqlalchemy_model_type()
        session = self._get_database_connector().create_session()

        # FIXME: It is an assumption that the Model property has the same name as SQLAlchemyModel.
        query_column = query_model.__dict__[property]
        result = session.query(query_model). \
            filter(query_column.in_(required_property_values)). \
            filter(query_model.is_current == 1).all()
        session.close()
        assert isinstance(result, list)
        return result

    def _get_database_connector(self) -> SQLAlchemyDatabaseConnector:
        """
        Gets the object through which database connections can be made.
        :return: the database connector
        """
        assert self._database_connector
        return self._database_connector

    def _get_sqlalchemy_model_type(self) -> SQLAlchemyModel:
        """
        Gets the SQLAlchemy model for which this mapper uses to perform queries with.
        :return: the SQLAlchemy model used by this mapper
        """
        if not self._type_cache:
            self._type_cache = get_equivalent_sqlalchemy_model_type(self._get_model_type())
        assert issubclass(self._type_cache, SQLAlchemyModel)
        return self._type_cache

    def _get_model_type(self) -> type:
        """
        Gets the type of models that this mapper deals with
        :return: the type of models that this mapper deals with
        """
        assert self._model_type
        return self._model_type


class SQLAlchemyLibraryMapper(SQLAlchemyMapper, LibraryMapper):
    def __init__(self, database_connector: SQLAlchemyDatabaseConnector):
        """
        Default constructor.
        :param database_connector: the database connector
        """
        super(SQLAlchemyLibraryMapper, self).__init__(database_connector, Library)


class SQLAlchemyMultiplexedLibraryMapper(SQLAlchemyMapper, MultiplexedLibraryMapper):
    def __init__(self, database_connector: SQLAlchemyDatabaseConnector):
        """
        Default constructor.
        :param database_connector: the database connector
        """
        super(SQLAlchemyMultiplexedLibraryMapper, self).__init__(database_connector, MultiplexedLibrary)


class SQLAlchemySampleMapper(SQLAlchemyMapper, SampleMapper):
    def __init__(self, database_connector: SQLAlchemyDatabaseConnector):
        """
        Default constructor.
        :param database_connector: the database connector
        """
        super(SQLAlchemySampleMapper, self).__init__(database_connector, Sample)


class SQLAlchemyWellMapper(SQLAlchemyMapper, WellMapper):
    def __init__(self, database_connector: SQLAlchemyDatabaseConnector):
        """
        Default constructor.
        :param database_connector: the database connector
        """
        super(SQLAlchemyWellMapper, self).__init__(database_connector, Well)


class SQLAlchemyStudyMapper(SQLAlchemyMapper, StudyMapper):
    def __init__(self, database_connector: SQLAlchemyDatabaseConnector):
        """
        Default constructor.
        :param database_connector: the database connector
        """
        super(SQLAlchemyStudyMapper, self).__init__(database_connector, Study)

    def get_associated_with_sample(self, sample_internal_ids: str) -> Study:
        session = self._get_database_connector().create_session()

        studies_samples = session.query(SQLAlchemyStudySamplesLink). \
            filter(SQLAlchemyStudySamplesLink.sample_internal_id.in_(sample_internal_ids)). \
            filter(SQLAlchemyStudySamplesLink.is_current == 1).all()

        if not studies_samples:
            return []

        study_ids = [study_sample.study_internal_id for study_sample in studies_samples]
        return self.get_by_id(study_ids)
